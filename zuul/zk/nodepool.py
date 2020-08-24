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
import time
from typing import Dict
from typing import TYPE_CHECKING, Optional

from kazoo.exceptions import NoNodeError, LockTimeout
from kazoo.recipe.cache import TreeCache
from kazoo.recipe.cache import TreeEvent
from kazoo.recipe.lock import Lock

import zuul.model
from zuul.zk.exceptions import LockException


class ZooKeeperNodepoolMixin:
    NODEPOOL_NODES_ROOT = "/nodepool/nodes"
    NODEPOOL_LAUNCHER_ROOT = "/nodepool/launchers"
    NODEPOOL_REQUEST_ROOT = '/nodepool/requests'
    NODEPOOL_REQUEST_LOCK_ROOT = "/nodepool/requests-lock"
    HOLD_REQUEST_ROOT = '/zuul/hold-requests'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The caching model we use is designed around handing out model
        # data as objects. To do this, we use two caches: one is a TreeCache
        # which contains raw znode data (among other details), and one for
        # storing that data serialized as objects. This allows us to return
        # objects from the APIs, and avoids calling the methods to serialize
        # the data into objects more than once.
        self.__hold_request_tree = None  # type: Optional[TreeCache]
        self.__cached_hold_requests =\
            {}  # type: Dict[str, zuul.model.HoldRequest]

    def _startCaching(self):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)
        if self.enable_cache:
            self.__hold_request_tree = TreeCache(self.client,
                                                 self.HOLD_REQUEST_ROOT)
            self.__hold_request_tree.listen_fault(self._cacheFaultListener)
            self.__hold_request_tree.listen(self._holdRequestCacheListener)
            self.__hold_request_tree.start()

    def _stopCaching(self):
        if self.__hold_request_tree is not None:
            self.__hold_request_tree.close()
            self.__hold_request_tree = None

    def __bytesToDict(self, data):
        return json.loads(data.decode('utf8'))

    def __launcherPath(self, launcher):
        return "%s/%s" % (self.NODEPOOL_LAUNCHER_ROOT, launcher)

    def __nodePath(self, node):
        return "%s/%s" % (self.NODEPOOL_NODES_ROOT, node)

    def getRegisteredLaunchers(self):
        """
        Get a list of all launchers that have registered with ZooKeeper.

        :returns: A list of Launcher objects, or empty list if none are found.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        try:
            launcher_ids = self.client\
                .get_children(self.NODEPOOL_LAUNCHER_ROOT)
        except NoNodeError:
            return []

        objs = []
        for launcher in launcher_ids:
            path = self.__launcherPath(launcher)
            try:
                data, _ = self.client.get(path)
            except NoNodeError:
                # launcher disappeared
                continue

            objs.append(Launcher.fromDict(self.__bytesToDict(data)))
        return objs

    def getNodes(self):
        """
        Get the current list of all nodes.

        :returns: A list of nodes.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        try:
            return self.client.get_children(self.NODEPOOL_NODES_ROOT)
        except NoNodeError:
            return []

    def __getNode(self, node):
        """
        Get the data for a specific node.

        :param str node: The node ID.

        :returns: The node data, or None if the node was not found.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = self.__nodePath(node)
        try:
            data, stat = self.client.get(path)
        except NoNodeError:
            return None
        if not data:
            return None

        d = self.__bytesToDict(data)
        d['id'] = node
        return d

    def nodeIterator(self):
        """
        Utility generator method for iterating through all nodes.
        """
        for node_id in self.getNodes():
            node = self.__getNode(node_id)
            if node:
                yield node

    def getHoldRequests(self):
        """
        Get the current list of all hold requests.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        try:
            return sorted(self.client.get_children(self.HOLD_REQUEST_ROOT))
        except NoNodeError:
            return []

    def getHoldRequest(self, hold_request_id):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = self.HOLD_REQUEST_ROOT + "/" + hold_request_id
        try:
            data, stat = self.client.get(path)
        except NoNodeError:
            return None
        if not data:
            return None

        obj = zuul.model.HoldRequest.fromDict(self._strToDict(data))
        obj.id = hold_request_id
        obj.stat = stat
        return obj

    def storeHoldRequest(self, request: zuul.model.HoldRequest):
        """
        Create or update a hold request.

        If this is a new request with no value for the `id` attribute of the
        passed in request, then `id` will be set with the unique request
        identifier after successful creation.

        :param HoldRequest request: Object representing the hold request.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        if request.id is None:
            path = self.client.create(
                self.HOLD_REQUEST_ROOT + "/",
                value=request.serialize(),
                sequence=True,
                makepath=True)
            request.id = path.split('/')[-1]
        else:
            path = self.HOLD_REQUEST_ROOT + "/" + request.id
            self.client.set(path, request.serialize())

    def __markHeldNodesAsUsed(self, request: zuul.model.HoldRequest):
        """
        Changes the state for each held node for the hold request to 'used'.

        :returns: True if all nodes marked USED, False otherwise.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
        for node_id in getHeldNodeIDs(request):
            node = self.__getNode(node_id)
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
                                   node_obj.id, request.id)
                failure = True
            finally:
                try:
                    if node_obj.lock:
                        self.unlockNode(node_obj)
                except Exception:
                    self.log.exception(
                        "Failed to unlock HELD node %s for request %s",
                        node_obj.id, request.id)

        return not failure

    def deleteHoldRequest(self, request: zuul.model.HoldRequest):
        """
        Delete a hold request.

        :param HoldRequest request: Object representing the hold request.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        if not self.__markHeldNodesAsUsed(request):
            self.log.info("Unable to delete hold request %s because "
                          "not all nodes marked as USED.", request.id)
            return

        path = self.HOLD_REQUEST_ROOT + "/" + request.id
        try:
            self.client.delete(path, recursive=True)
        except NoNodeError:
            pass

    def lockHoldRequest(self, request: zuul.model.HoldRequest,
                        blocking: bool=True, timeout: Optional[int]=None):
        """
        Lock a node request.

        This will set the `lock` attribute of the request object when the
        lock is successfully acquired.

        :param HoldRequest request: The hold request to lock.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not request.id:
            raise LockException(
                "Hold request without an ID cannot be locked: %s" % request)

        path = "%s/%s/lock" % (self.HOLD_REQUEST_ROOT, request.id)
        try:
            lock = Lock(self.client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            raise LockException("Timeout trying to acquire lock %s" % path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % path)

        request.lock = lock

    def unlockHoldRequest(self, request: zuul.model.HoldRequest):
        """
        Unlock a hold request.

        The request must already have been locked.

        :param HoldRequest request: The request to unlock.

        :raises: ZKLockException if the request is not currently locked.
        """
        if request.lock is None:
            raise LockException("Request %s does not hold a lock" % request)
        request.lock.release()
        request.lock = None

    def _holdRequestCacheListener(self, event):
        """
        Keep the hold request object cache in sync with the TreeCache.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        try:
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

            if event.event_type in (
                    TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED):
                # Requests with no data are invalid
                if not event.event_data.data:
                    return

                # Perform an in-place update of the already cached request
                d = self.__bytesToDict(event.event_data.data)
                old_request = self.__cached_hold_requests.get(request_id)
                if old_request:
                    if event.event_data.stat.version <= old_request.stat\
                            .version:
                        # Don't update to older data
                        return
                    old_request.updateFromDict(d)
                    old_request.stat = event.event_data.stat
                else:
                    request = zuul.model.HoldRequest.fromDict(d)
                    request.id = request_id
                    request.stat = event.event_data.stat
                    self.__cached_hold_requests[request_id] = request

            elif event.event_type == TreeEvent.NODE_REMOVED:
                try:
                    del self.__cached_hold_requests[request_id]
                except KeyError:
                    pass
        except Exception:
            self.log.exception(
                "Exception in hold request cache update for event: %s", event)

    def submitNodeRequest(self, node_request, watcher):
        """
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
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        node_request.created_time = time.time()
        data = node_request.toDict()

        path = '{}/{:0>3}-'.format(self.NODEPOOL_REQUEST_ROOT,
                                   node_request.priority)
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
        """
        Delete a request for nodes.

        :param NodeRequest node_request: A NodeRequest with the
            contents of the request.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = '%s/%s' % (self.NODEPOOL_REQUEST_ROOT, node_request.id)
        try:
            self.client.delete(path)
        except NoNodeError:
            pass

    def nodeRequestExists(self, node_request):
        """
        See if a NodeRequest exists in ZooKeeper.

        :param NodeRequest node_request: A NodeRequest to verify.

        :returns: True if the request exists, False otherwise.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = '%s/%s' % (self.NODEPOOL_REQUEST_ROOT, node_request.id)
        if self.client.exists(path):
            return True
        return False

    def storeNodeRequest(self, node_request):
        """
        Store the node request.

        The request is expected to already exist and is updated in its
        entirety.

        :param NodeRequest node_request: The request to update.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = '%s/%s' % (self.NODEPOOL_REQUEST_ROOT, node_request.id)
        self.client.set(path, self._dictToStr(node_request.toDict()))

    def updateNodeRequest(self, node_request, data=None):
        """
        Refresh an existing node request.

        :param NodeRequest node_request: The request to update.
        :param dict data: The data to use; query ZK if absent.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if data is None:
            path = '%s/%s' % (self.NODEPOOL_REQUEST_ROOT, node_request.id)
            data, stat = self.client.get(path)
        data = self._strToDict(data)
        request_nodes = list(node_request.nodeset.getNodes())
        for i, nodeid in enumerate(data.get('nodes', [])):
            request_nodes[i].id = nodeid
            self.__updateNode(request_nodes[i])
        node_request.updateFromDict(data)

    def storeNode(self, node):
        """
        Store the node.

        The node is expected to already exist and is updated in its
        entirety.

        :param Node node: The node to update.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = '%s/%s' % (self.NODEPOOL_NODES_ROOT, node.id)
        self.client.set(path, self._dictToStr(node.toDict()))

    def __updateNode(self, node):
        """
        Refresh an existing node.

        :param Node node: The node to update.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        node_path = '%s/%s' % (self.NODEPOOL_NODES_ROOT, node.id)
        node_data, node_stat = self.client.get(node_path)
        node_data = self._strToDict(node_data)
        node.updateFromDict(node_data)

    def lockNode(self, node, blocking=True, timeout=None):
        """
        Lock a node.

        This should be called as soon as a request is fulfilled and
        the lock held for as long as the node is in-use.  It can be
        used by nodepool to detect if Zuul has gone offline and the
        node should be reclaimed.

        :param Node node: The node which should be locked.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        lock_path = '%s/%s/lock' % (self.NODEPOOL_NODES_ROOT, node.id)
        try:
            lock = Lock(self.client, lock_path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            raise LockException(
                "Timeout trying to acquire lock %s" % lock_path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % lock_path)

        node.lock = lock

    def unlockNode(self, node):
        """
        Unlock a node.

        The node must already have been locked.

        :param Node node: The node which should be unlocked.
        """

        if node.lock is None:
            raise LockException("Node %s does not hold a lock" % (node,))
        node.lock.release()
        node.lock = None

    def lockNodeRequest(self, request, blocking=True, timeout=None):
        """
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
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = "%s/%s" % (self.NODEPOOL_REQUEST_LOCK_ROOT, request.id)
        try:
            lock = Lock(self.client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            raise LockException(
                "Timeout trying to acquire lock %s" % path)
        except NoNodeError:
            have_lock = False
            self.log.error("Request not found for locking: %s", request)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % path)

        request.lock = lock
        self.updateNodeRequest(request)

    def unlockNodeRequest(self, request):
        """
        Unlock a node request.

        The request must already have been locked.

        :param NodeRequest request: The request to unlock.

        :raises: ZKLockException if the request is not currently locked.
        """
        if request.lock is None:
            raise LockException(
                "Request %s does not hold a lock" % request)
        request.lock.release()
        request.lock = None

    def heldNodeCount(self, autohold_key):
        """
        Count the number of nodes being held for the given tenant/project/job.

        :param set autohold_key: A set with the tenant/project/job names.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        identifier = " ".join(autohold_key)
        try:
            nodes = self.client.get_children(self.NODEPOOL_NODES_ROOT)
        except NoNodeError:
            return 0

        count = 0
        for nodeid in nodes:
            node_path = '%s/%s' % (self.NODEPOOL_NODES_ROOT, nodeid)
            try:
                node_data, node_stat = self.client.get(node_path)
            except NoNodeError:
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


class Launcher:
    """
    Class to describe a nodepool launcher.
    """

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
