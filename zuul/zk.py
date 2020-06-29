# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import logging
import threading
import time
from typing import Dict, Callable, List, Any, Optional

from kazoo.client import KazooClient, KazooState
from kazoo import exceptions as kze
import kazoo.exceptions
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.cache import TreeCache, TreeEvent
from kazoo.recipe.lock import Lock, ReadLock, WriteLock
import zuul.model


class LockException(Exception):
    pass


class ZooKeeper(object):
    '''
    Class implementing the ZooKeeper interface.

    This class uses the facade design pattern to keep common interaction
    with the ZooKeeper API simple and consistent for the caller, and
    limits coupling between objects. It allows for more complex interactions
    by providing direct access to the client connection when needed (though
    that is discouraged). It also provides for a convenient entry point for
    testing only ZooKeeper interactions.
    '''

    log = logging.getLogger("zuul.zk.ZooKeeper")

    REQUEST_ROOT = '/nodepool/requests'
    REQUEST_LOCK_ROOT = "/nodepool/requests-lock"
    NODE_ROOT = '/nodepool/nodes'
    HOLD_REQUEST_ROOT = '/zuul/hold-requests'

    # Log zookeeper retry every 10 seconds
    retry_log_rate = 10

    def __init__(self, enable_cache: bool=True):
        '''
        Initialize the ZooKeeper object.

        :param bool enable_cache: When True, enables caching of ZooKeeper
            objects (e.g., HoldRequests).
        '''
        self.client = None  # type: Optional[KazooClient]
        self._became_lost = False  # type: bool
        self._last_retry_log = 0  # type: int
        self.enable_cache = enable_cache  # type: bool

        self.lockingLock = threading.Lock()
        self.event_watchers =\
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]
        self.layout_watcher =\
            None  # type: Optional[Callable[[str, str], None]]
        self.watched_tenants = []  # type: List[str]
        # The caching model we use is designed around handing out model
        # data as objects. To do this, we use two caches: one is a TreeCache
        # which contains raw znode data (among other details), and one for
        # storing that data serialized as objects. This allows us to return
        # objects from the APIs, and avoids calling the methods to serialize
        # the data into objects more than once.
        self._hold_request_tree = None  # type: Optional[TreeCache]
        self._cached_hold_requests =\
            {}  # type: Optional[Dict[str, zuul.model.HoldRequest]]

    def _dictToStr(self, data):
        return json.dumps(data).encode('utf8')

    def _strToDict(self, data):
        return json.loads(data.decode('utf8'))

    def _connection_listener(self, state):
        '''
        Listener method for Kazoo connection state changes.

        .. warning:: This method must not block.
        '''
        if state == KazooState.LOST:
            self.log.debug("ZooKeeper connection: LOST")
            self._became_lost = True
        elif state == KazooState.SUSPENDED:
            self.log.debug("ZooKeeper connection: SUSPENDED")
        else:
            self.log.debug("ZooKeeper connection: CONNECTED")

    @property
    def connected(self):
        return self.client.state == KazooState.CONNECTED

    @property
    def suspended(self):
        return self.client.state == KazooState.SUSPENDED

    @property
    def lost(self):
        return self.client.state == KazooState.LOST

    @property
    def didLoseConnection(self):
        return self._became_lost

    def resetLostFlag(self):
        self._became_lost = False

    def logConnectionRetryEvent(self):
        now = time.monotonic()
        if now - self._last_retry_log >= self.retry_log_rate:
            self.log.warning("Retrying zookeeper connection")
            self._last_retry_log = now

    def connect(self, hosts: str, read_only: bool=False, timeout: float=10.0,
                tls_cert: Optional[str]=None, tls_key: Optional[str]=None,
                tls_ca: Optional[str]=None):
        '''
        Establish a connection with ZooKeeper cluster.

        Convenience method if a pre-existing ZooKeeper connection is not
        supplied to the ZooKeeper object at instantiation time.

        :param str hosts: Comma-separated list of hosts to connect to (e.g.
            127.0.0.1:2181,127.0.0.1:2182,[::1]:2183).
        :param bool read_only: If True, establishes a read-only connection.
        :param float timeout: The ZooKeeper session timeout, in
            seconds (default: 10.0).
        :param str tls_key: Path to TLS key
        :param str tls_cert: Path to TLS cert
        :param str tls_ca: Path to TLS CA cert
        '''

        if self.client is None:
            args = dict(hosts=hosts, read_only=read_only, timeout=timeout)
            if tls_key:
                args['use_ssl'] = True
                args['keyfile'] = tls_key
                args['certfile'] = tls_cert
                args['ca'] = tls_ca
            self.client = KazooClient(**args)
            self.client.add_listener(self._connection_listener)
            # Manually retry initial connection attempt
            while True:
                try:
                    self.client.start(1)
                    break
                except KazooTimeoutError:
                    self.logConnectionRetryEvent()

        if self.enable_cache:
            self._hold_request_tree = TreeCache(self.client,
                                                self.HOLD_REQUEST_ROOT)
            self._hold_request_tree.listen_fault(self.cacheFaultListener)
            self._hold_request_tree.listen(self.holdRequestCacheListener)
            self._hold_request_tree.start()

    def cacheFaultListener(self, e):
        self.log.exception(e)

    def holdRequestCacheListener(self, event):
        '''
        Keep the hold request object cache in sync with the TreeCache.
        '''
        try:
            self._holdRequestCacheListener(event)
        except Exception:
            self.log.exception(
                "Exception in hold request cache update for event: %s", event)

    def _holdRequestCacheListener(self, event):
        if hasattr(event.event_data, 'path'):
            # Ignore root node
            path = event.event_data.path
            if path == self.HOLD_REQUEST_ROOT:
                return

        if event.event_type not in (TreeEvent.NODE_ADDED,
                                    TreeEvent.NODE_UPDATED,
                                    TreeEvent.NODE_REMOVED):
            return

        path = event.event_data.path
        request_id = path.rsplit('/', 1)[1]

        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED):
            # Requests with no data are invalid
            if not event.event_data.data:
                return

            # Perform an in-place update of the already cached request
            d = self._bytesToDict(event.event_data.data)
            old_request = self._cached_hold_requests.get(request_id)
            if old_request:
                if event.event_data.stat.version <= old_request.stat.version:
                    # Don't update to older data
                    return
                old_request.updateFromDict(d)
                old_request.stat = event.event_data.stat
            else:
                request = zuul.model.HoldRequest.fromDict(d)
                request.id = request_id
                request.stat = event.event_data.stat
                self._cached_hold_requests[request_id] = request

        elif event.event_type == TreeEvent.NODE_REMOVED:
            try:
                del self._cached_hold_requests[request_id]
            except KeyError:
                pass

    def disconnect(self):
        '''
        Close the ZooKeeper cluster connection.

        You should call this method if you used connect() to establish a
        cluster connection.
        '''
        if self._hold_request_tree is not None:
            self._hold_request_tree.close()
            self._hold_request_tree = None

        if self.client is not None and self.client.connected:
            self.client.stop()
            self.client.close()
            self.client = None

    def resetHosts(self, hosts):
        '''
        Reset the ZooKeeper cluster connection host list.

        :param str hosts: Comma-separated list of hosts to connect to (e.g.
            127.0.0.1:2181,127.0.0.1:2182,[::1]:2183).
        '''
        if self.client is not None:
            self.client.set_hosts(hosts=hosts)

    def submitNodeRequest(self, node_request, watcher):
        '''
        Submit a request for nodes to Nodepool.

        :param NodeRequest node_request: A NodeRequest with the
            contents of the request.

        :param callable watcher: A callable object that will be
            invoked each time the request is updated.  It is called
            with two arguments: (node_request, deleted) where
            node_request is the same argument passed to this method,
            and deleted is a boolean which is True if the node no
            longer exists (notably, this will happen on disconnection
            from ZooKeeper).  The watcher should return False when
            further updates are no longer necessary.
        '''
        node_request.created_time = time.time()
        data = node_request.toDict()

        path = '{}/{:0>3}-'.format(self.REQUEST_ROOT, node_request.priority)
        path = self.client.create(path, self._dictToStr(data),
                                  makepath=True,
                                  sequence=True, ephemeral=True)
        reqid = path.split("/")[-1]
        node_request.id = reqid

        def callback(data, stat):
            if data:
                self.updateNodeRequest(node_request, data)
            deleted = (data is None)  # data *are* none
            return watcher(node_request, deleted)

        self.client.DataWatch(path, callback)

    def deleteNodeRequest(self, node_request):
        '''
        Delete a request for nodes.

        :param NodeRequest node_request: A NodeRequest with the
            contents of the request.
        '''

        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        try:
            self.client.delete(path)
        except kze.NoNodeError:
            pass

    def nodeRequestExists(self, node_request):
        '''
        See if a NodeRequest exists in ZooKeeper.

        :param NodeRequest node_request: A NodeRequest to verify.

        :returns: True if the request exists, False otherwise.
        '''
        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        if self.client.exists(path):
            return True
        return False

    def storeNodeRequest(self, node_request):
        '''Store the node request.

        The request is expected to already exist and is updated in its
        entirety.

        :param NodeRequest node_request: The request to update.
        '''

        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        self.client.set(path, self._dictToStr(node_request.toDict()))

    def updateNodeRequest(self, node_request, data=None):
        '''Refresh an existing node request.

        :param NodeRequest node_request: The request to update.
        :param dict data: The data to use; query ZK if absent.
        '''
        if data is None:
            path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
            data, stat = self.client.get(path)
        data = self._strToDict(data)
        request_nodes = list(node_request.nodeset.getNodes())
        for i, nodeid in enumerate(data.get('nodes', [])):
            request_nodes[i].id = nodeid
            self.updateNode(request_nodes[i])
        node_request.updateFromDict(data)

    def storeNode(self, node):
        '''Store the node.

        The node is expected to already exist and is updated in its
        entirety.

        :param Node node: The node to update.
        '''

        path = '%s/%s' % (self.NODE_ROOT, node.id)
        self.client.set(path, self._dictToStr(node.toDict()))

    def updateNode(self, node):
        '''Refresh an existing node.

        :param Node node: The node to update.
        '''

        node_path = '%s/%s' % (self.NODE_ROOT, node.id)
        node_data, node_stat = self.client.get(node_path)
        node_data = self._strToDict(node_data)
        node.updateFromDict(node_data)

    def lockNode(self, node, blocking=True, timeout=None):
        '''
        Lock a node.

        This should be called as soon as a request is fulfilled and
        the lock held for as long as the node is in-use.  It can be
        used by nodepool to detect if Zuul has gone offline and the
        node should be reclaimed.

        :param Node node: The node which should be locked.
        '''

        lock_path = '%s/%s/lock' % (self.NODE_ROOT, node.id)
        try:
            lock = Lock(self.client, lock_path)
            have_lock = lock.acquire(blocking, timeout)
        except kze.LockTimeout:
            raise LockException(
                "Timeout trying to acquire lock %s" % lock_path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % lock_path)

        node.lock = lock

    def unlockNode(self, node):
        '''
        Unlock a node.

        The node must already have been locked.

        :param Node node: The node which should be unlocked.
        '''

        if node.lock is None:
            raise LockException("Node %s does not hold a lock" % (node,))
        node.lock.release()
        node.lock = None

    def lockNodeRequest(self, request, blocking=True, timeout=None):
        '''
        Lock a node request.

        This will set the `lock` attribute of the request object when the
        lock is successfully acquired.

        :param NodeRequest request: The request to lock.
        :param bool blocking: Whether or not to block on trying to
            acquire the lock
        :param int timeout: When blocking, how long to wait for the lock
            to get acquired. None, the default, waits forever.

        :raises: TimeoutException if we failed to acquire the lock when
            blocking with a timeout. ZKLockException if we are not blocking
            and could not get the lock, or a lock is already held.
        '''

        path = "%s/%s" % (self.REQUEST_LOCK_ROOT, request.id)
        try:
            lock = Lock(self.client, path)
            have_lock = lock.acquire(blocking, timeout)
        except kze.LockTimeout:
            raise LockException(
                "Timeout trying to acquire lock %s" % path)
        except kze.NoNodeError:
            have_lock = False
            self.log.error("Request not found for locking: %s", request)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % path)

        request.lock = lock
        self.updateNodeRequest(request)

    def unlockNodeRequest(self, request):
        '''
        Unlock a node request.

        The request must already have been locked.

        :param NodeRequest request: The request to unlock.

        :raises: ZKLockException if the request is not currently locked.
        '''
        if request.lock is None:
            raise LockException(
                "Request %s does not hold a lock" % request)
        request.lock.release()
        request.lock = None

    def heldNodeCount(self, autohold_key):
        '''
        Count the number of nodes being held for the given tenant/project/job.

        :param set autohold_key: A set with the tenant/project/job names.
        '''
        identifier = " ".join(autohold_key)
        try:
            nodes = self.client.get_children(self.NODE_ROOT)
        except kze.NoNodeError:
            return 0

        count = 0
        for nodeid in nodes:
            node_path = '%s/%s' % (self.NODE_ROOT, nodeid)
            try:
                node_data, node_stat = self.client.get(node_path)
            except kze.NoNodeError:
                # Node got removed on us. Just ignore.
                continue

            if not node_data:
                self.log.warning("Node ID %s has no data", nodeid)
                continue
            node_data = self._strToDict(node_data)
            if (node_data['state'] == zuul.model.STATE_HOLD and
                    node_data.get('hold_job') == identifier):
                count += 1
        return count

    # Copy of nodepool/zk.py begins here
    NODE_ROOT = "/nodepool/nodes"
    LAUNCHER_ROOT = "/nodepool/launchers"

    def _bytesToDict(self, data):
        return json.loads(data.decode('utf8'))

    def _launcherPath(self, launcher):
        return "%s/%s" % (self.LAUNCHER_ROOT, launcher)

    def _nodePath(self, node):
        return "%s/%s" % (self.NODE_ROOT, node)

    def getRegisteredLaunchers(self):
        '''
        Get a list of all launchers that have registered with ZooKeeper.

        :returns: A list of Launcher objects, or empty list if none are found.
        '''
        try:
            launcher_ids = self.client.get_children(self.LAUNCHER_ROOT)
        except kze.NoNodeError:
            return []

        objs = []
        for launcher in launcher_ids:
            path = self._launcherPath(launcher)
            try:
                data, _ = self.client.get(path)
            except kze.NoNodeError:
                # launcher disappeared
                continue

            objs.append(Launcher.fromDict(self._bytesToDict(data)))
        return objs

    def getNodes(self):
        '''
        Get the current list of all nodes.

        :returns: A list of nodes.
        '''
        try:
            return self.client.get_children(self.NODE_ROOT)
        except kze.NoNodeError:
            return []

    def getNode(self, node):
        '''
        Get the data for a specific node.

        :param str node: The node ID.

        :returns: The node data, or None if the node was not found.
        '''
        path = self._nodePath(node)
        try:
            data, stat = self.client.get(path)
        except kze.NoNodeError:
            return None
        if not data:
            return None

        d = self._bytesToDict(data)
        d['id'] = node
        return d

    def nodeIterator(self):
        '''
        Utility generator method for iterating through all nodes.
        '''
        for node_id in self.getNodes():
            node = self.getNode(node_id)
            if node:
                yield node

    def getHoldRequests(self):
        '''
        Get the current list of all hold requests.
        '''
        try:
            return sorted(self.client.get_children(self.HOLD_REQUEST_ROOT))
        except kze.NoNodeError:
            return []

    def getHoldRequest(self, hold_request_id):
        path = self.HOLD_REQUEST_ROOT + "/" + hold_request_id
        try:
            data, stat = self.client.get(path)
        except kze.NoNodeError:
            return None
        if not data:
            return None

        obj = zuul.model.HoldRequest.fromDict(self._strToDict(data))
        obj.id = hold_request_id
        obj.stat = stat
        return obj

    def storeHoldRequest(self, hold_request):
        '''
        Create or update a hold request.

        If this is a new request with no value for the `id` attribute of the
        passed in request, then `id` will be set with the unique request
        identifier after successful creation.

        :param HoldRequest hold_request: Object representing the hold request.
        '''
        if hold_request.id is None:
            path = self.client.create(
                self.HOLD_REQUEST_ROOT + "/",
                value=hold_request.serialize(),
                sequence=True,
                makepath=True)
            hold_request.id = path.split('/')[-1]
        else:
            path = self.HOLD_REQUEST_ROOT + "/" + hold_request.id
            self.client.set(path, hold_request.serialize())

    def _markHeldNodesAsUsed(self, hold_request):
        '''
        Changes the state for each held node for the hold request to 'used'.

        :returns: True if all nodes marked USED, False otherwise.
        '''
        def getHeldNodeIDs(request):
            node_ids = []
            for data in request.nodes:
                # TODO(Shrews): Remove type check at some point.
                # When autoholds were initially changed to be stored in ZK,
                # the node IDs were originally stored as a list of strings.
                # A later change embedded them within a dict. Handle both
                # cases here to deal with the upgrade.
                if isinstance(data, dict):
                    node_ids += data['nodes']
                else:
                    node_ids.append(data)
            return node_ids

        failure = False
        for node_id in getHeldNodeIDs(hold_request):
            node = self.getNode(node_id)
            if not node or node['state'] == zuul.model.STATE_USED:
                continue

            node['state'] = zuul.model.STATE_USED

            name = None
            label = None
            if 'name' in node:
                name = node['name']
            if 'label' in node:
                label = node['label']

            node_obj = zuul.model.Node(name, label)
            node_obj.updateFromDict(node)

            try:
                self.lockNode(node_obj, blocking=False)
                self.storeNode(node_obj)
            except Exception:
                self.log.exception("Cannot change HELD node state to USED "
                                   "for node %s in request %s",
                                   node_obj.id, hold_request.id)
                failure = True
            finally:
                try:
                    if node_obj.lock:
                        self.unlockNode(node_obj)
                except Exception:
                    self.log.exception(
                        "Failed to unlock HELD node %s for request %s",
                        node_obj.id, hold_request.id)

        return not failure

    def deleteHoldRequest(self, hold_request):
        '''
        Delete a hold request.

        :param HoldRequest hold_request: Object representing the hold request.
        '''
        if not self._markHeldNodesAsUsed(hold_request):
            self.log.info("Unable to delete hold request %s because "
                          "not all nodes marked as USED.", hold_request.id)
            return

        path = self.HOLD_REQUEST_ROOT + "/" + hold_request.id
        try:
            self.client.delete(path, recursive=True)
        except kze.NoNodeError:
            pass

    def lockHoldRequest(self, request, blocking=True, timeout=None):
        '''
        Lock a node request.

        This will set the `lock` attribute of the request object when the
        lock is successfully acquired.

        :param HoldRequest request: The hold request to lock.
        '''
        if not request.id:
            raise LockException(
                "Hold request without an ID cannot be locked: %s" % request)

        path = "%s/%s/lock" % (self.HOLD_REQUEST_ROOT, request.id)
        try:
            lock = Lock(self.client, path)
            have_lock = lock.acquire(blocking, timeout)
        except kze.LockTimeout:
            raise LockException(
                "Timeout trying to acquire lock %s" % path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % path)

        request.lock = lock

    def unlockHoldRequest(self, request):
        '''
        Unlock a hold request.

        The request must already have been locked.

        :param HoldRequest request: The request to unlock.

        :raises: ZKLockException if the request is not currently locked.
        '''
        if request.lock is None:
            raise LockException(
                "Request %s does not hold a lock" % request)
        request.lock.release()
        request.lock = None

    # Scheduler part begins here

    CONFIG_ROOT = "/zuul"
    # Node content max size: keep ~100kB as a reserve form the 1MB limit
    CONFIG_MAX_SIZE = 1024 * 1024 - 100 * 1024

    def _getZuulNodePath(self, *args: str) -> str:
        return "/".join(filter(lambda s: s is not None and s != '',
                               [self.CONFIG_ROOT] + list(args)))

    def _getConfigPartContent(self, parent, child) -> str:
        node = "%s/%s" % (parent, child)
        return self.client.get(node)[0].decode(encoding='UTF-8')\
            if self.client and self.client.exists(node) else ''

    def _getZuulEventConnectionPath(self, connection_name: str,
                                    path: str, sequence: Optional[str]=None):
        return self._getZuulNodePath('events', 'connection',
                                     connection_name, path, sequence or '')

    def acquireLock(self, lock: Lock, keepLocked: bool = False):
        # There are 2 reasons for the "locking" lock:
        # 1) In production to prevent simultaneous acquisition of ZK locks
        #    from different threads, which may fail
        # 2) In tests to prevent events being popped or pushed while waiting
        #    for scheduler to settle
        #
        # The parameter keepLocked should be only set to True in the waiting
        # to settle. This will allow multiple entry and lock of different
        # connection in one scheduler instance from test thread and at the same
        # time block lock request from runtime threads.
        # If set to True, the lockingLock needs to be unlocked manually
        # afterwards.
        if not keepLocked or not self.lockingLock.locked():
            self.lockingLock.acquire()
        locked = False
        try:
            while not locked:
                try:  # Make sure request does not hang
                    lock.acquire(timeout=10.0)
                    locked = True
                except kazoo.exceptions.LockTimeout:
                    self.log.debug("Could not acquire lock %s" % lock.path)
                    raise
        finally:
            if not keepLocked and self.lockingLock.locked():
                self.lockingLock.release()

    def _getConnectionEventReadLock(self, connection_name: str)\
            -> ReadLock:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock_node = self._getZuulEventConnectionPath(connection_name, '')
        return self.client.ReadLock(lock_node)

    def _getConnectionEventWriteLock(self, connection_name: str)\
            -> WriteLock:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock_node = self._getZuulEventConnectionPath(connection_name, '')
        return self.client.WriteLock(lock_node)

    def watchConnectionEvents(self, connection_name: str,
                              watch: Callable[[List[str]], None]):
        if connection_name not in self.event_watchers:
            self.event_watchers[connection_name] = [watch]

            if not self.client:
                raise Exception("No zookeeper client!")

            path = self._getZuulEventConnectionPath(connection_name, 'nodes')
            self.client.ensure_path(path)

            def watch_children(children):
                if len(children) > 0:
                    for watcher in self.event_watchers[connection_name]:
                        watcher(children)

            self.client.ChildrenWatch(path, watch_children)
        else:
            self.event_watchers[connection_name].append(watch)

    def unwatchConnectionEvents(self, connection_name: str):
        if connection_name in self.event_watchers:
            del self.event_watchers[connection_name]

    def hasConnectionEvents(self, connection_name: str,
                            keepLocked: bool = False) -> bool:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock = self._getConnectionEventReadLock(connection_name)
        self.acquireLock(lock, keepLocked)
        self.log.debug('hasConnectionEvents[%s]: locked' % connection_name)
        path = self._getZuulEventConnectionPath(connection_name, 'nodes')
        try:
            count = len(self.client.get_children(path))
            self.log.debug('hasConnectionEvents[%s]: %s' %
                           (connection_name, count))
            return count > 0
        except kazoo.exceptions.NoNodeError as e:
            self.log.debug('hasConnectionEvents[%s]: NoNodeError: %s' %
                           (connection_name, e))
            return False
        finally:
            lock.release()
            self.log.debug('hasConnectionEvents[%s]: released' %
                           connection_name)

    def popConnectionEvents(self, connection_name: str):
        if not self.client:
            raise Exception("No zookeeper client!")

        class EventWrapper:
            def __init__(self, zk, conn_name: str):
                self.__zk = zk
                self.__connection_name = conn_name
                self.__lock = self.__zk._getConnectionEventWriteLock(conn_name)

            def __enter__(self):
                self.__zk.acquireLock(self.__lock)
                self.__zk.log.debug('popConnectionEvents: locked')
                events = []
                path = self.__zk._getZuulEventConnectionPath(
                    self.__connection_name, 'nodes')
                children = self.__zk.client.get_children(path)

                for child in sorted(children):
                    path = self.__zk._getZuulEventConnectionPath(
                        self.__connection_name, 'nodes', child)
                    data = self.__zk.client.get(path)[0]
                    event = json.loads(data.decode(encoding='utf-8'))
                    events.append(event)
                    self.__zk.client.delete(path)
                return events

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.__lock.release()
                self.__zk.log.debug('popConnectionEvents: released')

        return EventWrapper(self, connection_name)

    def pushConnectionEvent(self, connection_name: str, event: Any):
        if not self.client:
            raise Exception("No zookeeper client!")
        lock = self._getConnectionEventWriteLock(connection_name)
        self.acquireLock(lock)
        self.log.debug('pushConnectionEvent: locked')
        try:
            path = self._getZuulEventConnectionPath(
                connection_name, 'nodes') + '/'
            self.client.create(path, json.dumps(event).encode('utf-8'),
                               sequence=True, makepath=True)
        finally:
            lock.release()
            self.log.debug('pushConnectionEvent: released')

    def getLayoutHash(self, tenant: str) -> Optional[str]:
        """
        Get tenant's layout version.

        A layout version is a hash over all relevant files for the given
        tenant.

        :param tenant: Tentant
        :return: Tenant's layout relevant files hash
        """
        if self.client:
            lock_node = self._getZuulNodePath('layout')
            with self.client.ReadLock(lock_node):
                node = self._getZuulNodePath('layout', '_hashes_', tenant)
                layout_hash = self.client.get(node)[0]\
                    .decode(encoding='UTF-8')\
                    if self.client.exists(node) else None
                self.log.debug("[GET] Layout hash for %s: %s" %
                               (tenant, layout_hash))
                return layout_hash
        else:
            self.log.error("No zookeeper client!")
            return None

    def setLayoutHash(self, tenant: str, layout_hash: str) -> None:
        if self.client:
            lock_node = self._getZuulNodePath('layout')
            with self.client.WriteLock(lock_node):
                node = self._getZuulNodePath('layout', '_hashes_', tenant)
                stat = self.client.exists(node)
                if stat is None:
                    self.client.create(
                        node, layout_hash.encode(encoding='UTF-8'),
                        makepath=True)
                else:
                    self.client.set(
                        node, layout_hash.encode(encoding='UTF-8'),
                        version=stat.version)
                self.log.debug("[SET] Layout hash for %s: %s" %
                               (tenant, layout_hash))
        else:
            self.log.error("No zookeeper client!")

    def watchLayoutHashes(self, watch: Callable[[str, str], None]):
        if not self.client:
            raise Exception("No zookeeper client!")
        self.layout_watcher = watch

        path = self._getZuulNodePath('layout', '_hashes_')
        self.client.ensure_path(path)

        class Watcher:
            def __init__(self, node_name: str):
                self.node_name = node_name

            def __call__(this, data, stat: ZnodeStat, event):
                if self.layout_watcher is not None:
                    self.layout_watcher(this.node_name,
                                        data.decode(encoding='UTF-8'))

        def watch_children(children):
            for child in children:
                if child not in self.watched_tenants:
                    self.watched_tenants.append(child)
                    hash_path = self._getZuulNodePath(
                        'layout', '_hashes_', child)
                    self.client.DataWatch(hash_path, Watcher(child))
                    data, stat = self.client.get(hash_path)
                    self.layout_watcher(child, data.decode(encoding='UTF-8'))

        for node in self.client.get_children(path):
            self.watched_tenants.append(node)
            hash_path = self._getZuulNodePath('layout', '_hashes_', node)
            self.client.DataWatch(hash_path, Watcher(node))

        self.client.ChildrenWatch(path, watch_children)

    def getConfigReadLock(self) -> Optional[ReadLock]:
        lock_node = self._getZuulNodePath('config')
        return self.client.WriteLock(lock_node) if self.client else None

    def getConfigWriteLock(self) -> Optional[WriteLock]:
        lock_node = self._getZuulNodePath('config')
        return self.client.WriteLock(lock_node) if self.client else None

    def loadConfig(self, tenant: str, project: str, branch: str, path: str,
                   use_lock: bool=True) -> Optional[str]:
        """
        Load unparsed config from zookeeper under
        /zuul/config/<tenant>/<project>/<branch>/<path-to-config>/<shard>

        :param tenant: Tenant name
        :param project: Project name
        :param branch: Branch
        :param path: Path
        :param use_lock: Whether the operation should be read-locked
        :return: The unparsed config an its version as a tuple or None.
        """
        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.getConfigReadLock() if use_lock else None
        if lock:
            lock.acquire()
        try:
            node = self._getZuulNodePath('config', tenant, project,
                                         branch, path)
            content = "".join(
                map(lambda c: self._getConfigPartContent(node, c),
                    self.client.get_children(node)))\
                if self.client.exists(node) else None
            return content
        finally:
            if lock:
                lock.release()

    def saveConfig(self, tenant: str, project: str, branch: str, path: str,
                   data: Optional[str]) -> None:
        """
        Saves unparsed configuration to zookeeper under
        /zuul/config/<tenant>/<project>/<branch>/<path-to-config>/<shard>

        An update only happens if the currently stored content differs from
        the provided in `data` param.

        This operation needs to be explicitly locked using lock from
        `getConfigWriteLock`

        :param tenant: Tenant name
        :param project: Project name
        :param branch: Branch
        :param path: Path
        :param data: Unparsed configuration yaml
        """
        if not self.client:
            raise Exception("No zookeeper client!")

        current = self.loadConfig(tenant, project, branch, path,
                                  use_lock=False)
        if current != data:
            content = data.encode(encoding='UTF-8')\
                if data is not None else None

            node = self._getZuulNodePath('config', tenant, project,
                                         branch, path)
            exists = self.client.exists(node)

            if exists:
                for child in self.client.get_children(node):
                    try:
                        self.log.debug("Deleting: %s/%s" % (node, child))
                        self.client.delete("%s/%s" % (node, child),
                                           recursive=True)
                    except kze.NoNodeError:
                        pass

            if content is not None:
                self.client.ensure_path(node)
                chunks = [content[i:i + self.CONFIG_MAX_SIZE]
                          for i in range(0, len(content),
                                         self.CONFIG_MAX_SIZE)]
                for i, chunk in enumerate(chunks):
                    self.log.debug("Creating: %s/%d" % (node, i))
                    self.client.create("%s/%d" % (node, i), chunk)
            elif exists:
                self.client.delete(node)


class Launcher():
    '''
    Class to describe a nodepool launcher.
    '''

    def __init__(self):
        self.id = None
        self._supported_labels = set()

    def __eq__(self, other):
        if isinstance(other, Launcher):
            return (self.id == other.id and
                    self.supported_labels == other.supported_labels)
        else:
            return False

    @property
    def supported_labels(self):
        return self._supported_labels

    @supported_labels.setter
    def supported_labels(self, value):
        if not isinstance(value, set):
            raise TypeError("'supported_labels' attribute must be a set")
        self._supported_labels = value

    @staticmethod
    def fromDict(d):
        obj = Launcher()
        obj.id = d.get('id')
        obj.supported_labels = set(d.get('supported_labels', []))
        return obj
