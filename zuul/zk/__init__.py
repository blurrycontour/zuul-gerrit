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

import configparser
import json
import logging
import time
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from kazoo.client import KazooClient, KazooState
from kazoo import exceptions as kze
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.recipe.cache import TreeCache, TreeEvent
from kazoo.recipe.lock import Lock

import zuul.model
from zuul.lib.config import get_default
from zuul.zk.builds import ZooKeeperBuildsMixin
from zuul.zk.exceptions import LockException
from zuul.zk.nodepool import ZooKeeperNodepoolMixin
from zuul.zk.zuul import ZooKeeperZuulMixin


class ZooKeeper(ZooKeeperNodepoolMixin,
                ZooKeeperZuulMixin,
                ZooKeeperBuildsMixin,
                object):
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

        # The caching model we use is designed around handing out model
        # data as objects. To do this, we use two caches: one is a TreeCache
        # which contains raw znode data (among other details), and one for
        # storing that data serialized as objects. This allows us to return
        # objects from the APIs, and avoids calling the methods to serialize
        # the data into objects more than once.
        self._hold_request_tree = None  # type: Optional[TreeCache]
        self._cached_hold_requests =\
            {}  # type: Optional[Dict[str, zuul.model.HoldRequest]]

        self.node_watchers =\
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]

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


def connect_zookeeper(config: configparser.ConfigParser) -> ZooKeeper:
    zookeeper = ZooKeeper(enable_cache=True)
    zookeeper_hosts = get_default(config, 'zookeeper', 'hosts', None)
    if not zookeeper_hosts:
        raise Exception("The zookeeper hosts config value is required")
    zookeeper_tls_key = get_default(config, 'zookeeper', 'tls_key')
    zookeeper_tls_cert = get_default(config, 'zookeeper', 'tls_cert')
    zookeeper_tls_ca = get_default(config, 'zookeeper', 'tls_ca')
    zookeeper_timeout = float(get_default(config, 'zookeeper',
                                          'session_timeout', 10.0))
    zookeeper.connect(
        hosts=zookeeper_hosts,
        timeout=zookeeper_timeout,
        tls_cert=zookeeper_tls_cert,
        tls_key=zookeeper_tls_key,
        tls_ca=zookeeper_tls_ca)
    return zookeeper
