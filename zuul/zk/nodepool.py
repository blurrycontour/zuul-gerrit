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
import time
from typing import Dict, Optional, List

from kazoo.exceptions import NoNodeError, LockTimeout
from kazoo.recipe.cache import TreeCache
from kazoo.recipe.cache import TreeEvent
from kazoo.recipe.lock import Lock

import zuul.model
from zuul.model import HoldRequest, Node, NodeRequest, NodeSet
from zuul.zk import ZooKeeperClient, ZooKeeperBase
from zuul.zk.exceptions import LockException


class ZooKeeperNodepool(ZooKeeperBase):
    """
    Class implementing Nodepool related ZooKeeper interface.
    """
    NODES_ROOT = "/nodepool/nodes"
    LAUNCHER_ROOT = "/nodepool/launchers"
    REQUEST_ROOT = '/nodepool/requests'
    REQUEST_LOCK_ROOT = "/nodepool/requests-lock"
    HOLD_REQUEST_ROOT = '/zuul/hold-requests'

    log = logging.getLogger("zuul.zk.nodepool.ZooKeeperNodepool")

    def __init__(self, client: ZooKeeperClient, enable_cache: bool = True):
        super().__init__(client)
        self.enable_cache = enable_cache  # type: bool
        # The caching model we use is designed around handing out model
        # data as objects. To do this, we use two caches: one is a TreeCache
        # which contains raw znode data (among other details), and one for
        # storing that data serialized as objects. This allows us to return
        # objects from the APIs, and avoids calling the methods to serialize
        # the data into objects more than once.
        self._hold_request_tree: Optional[TreeCache] = None
        self._cached_hold_requests: Optional[Dict[str, HoldRequest]] = {}
        if self.client.connected:
            self._onConnect()

    def _onConnect(self):
        if self.enable_cache:
            self._hold_request_tree = TreeCache(self.kazoo_client,
                                                self.HOLD_REQUEST_ROOT)
            self._hold_request_tree.listen_fault(self._cacheFaultListener)
            self._hold_request_tree.listen(self._holdRequestCacheListener)
            self._hold_request_tree.start()

    def _onDisconnect(self):
        if self._hold_request_tree is not None:
            self._hold_request_tree.close()
            self._hold_request_tree = None

    def _launcherPath(self, launcher):
        return "%s/%s" % (self.LAUNCHER_ROOT, launcher)

    def _nodePath(self, node):
        return "%s/%s" % (self.NODES_ROOT, node)

    def _cacheFaultListener(self, e):
        self.log.exception(e)

    def getRegisteredLaunchers(self):
        """
        Get a list of all launchers that have registered with ZooKeeper.

        :returns: A list of Launcher objects, or empty list if none are found.
        """
        try:
            launcher_ids = self.kazoo_client\
                .get_children(self.LAUNCHER_ROOT)
        except NoNodeError:
            return []

        objs = []
        for launcher in launcher_ids:
            path = self._launcherPath(launcher)
            try:
                data, _ = self.kazoo_client.get(path)
            except NoNodeError:
                # launcher disappeared
                continue

            objs.append(Launcher.fromDict(json.loads(data.decode('utf8'))))
        return objs

    def getNodes(self):
        """
        Get the current list of all nodes.

        :returns: A list of nodes.
        """
        try:
            return self.kazoo_client.get_children(self.NODES_ROOT)
        except NoNodeError:
            return []

    def _getNode(self, node):
        """
        Get the data for a specific node.

        :param str node: The node ID.

        :returns: The node data, or None if the node was not found.
        """
        path = self._nodePath(node)
        try:
            data, stat = self.kazoo_client.get(path)
        except NoNodeError:
            return None
        if not data:
            return None

        d = json.loads(data.decode('utf8'))
        d['id'] = node
        return d

    def nodeIterator(self):
        """
        Utility generator method for iterating through all nodes.
        """
        for node_id in self.getNodes():
            node = self._getNode(node_id)
            if node:
                yield node

    def getHoldRequests(self):
        """
        Get the current list of all hold requests.
        """

        try:
            return sorted(self.kazoo_client
                          .get_children(self.HOLD_REQUEST_ROOT))
        except NoNodeError:
            return []

    def getHoldRequest(self, hold_request_id):
        # To be friendly, zero pad if this request came from a client
        # call, where the user might have done "zuul autohold-delete
        # 123" thinking that would match the "0000000123" shown in
        # "autohold-list".
        #
        #  "A sequential node will be given the specified path plus a
        #  suffix i where i is the current sequential number of the
        #  node. The sequence number is always fixed length of 10
        #  digits, 0 padded. Once such a node is created, the
        #  sequential number will be incremented by one."
        if len(hold_request_id) != 10:
            hold_request_id = hold_request_id.rjust(10, '0')

        path = self.HOLD_REQUEST_ROOT + "/" + hold_request_id
        try:
            data, stat = self.kazoo_client.get(path)
        except NoNodeError:
            return None
        if not data:
            return None

        obj = HoldRequest.fromDict(json.loads(data.decode('utf8')))
        obj.id = hold_request_id
        obj.stat = stat
        return obj

    def storeHoldRequest(self, request: HoldRequest):
        """
        Create or update a hold request.

        If this is a new request with no value for the `id` attribute of the
        passed in request, then `id` will be set with the unique request
        identifier after successful creation.

        :param HoldRequest request: Object representing the hold request.
        """
        if request.id is None:
            path = self.kazoo_client.create(
                self.HOLD_REQUEST_ROOT + "/",
                value=request.serialize(),
                sequence=True,
                makepath=True)
            request.id = path.split('/')[-1]
        else:
            path = self.HOLD_REQUEST_ROOT + "/" + request.id
            self.kazoo_client.set(path, request.serialize())

    def _markHeldNodesAsUsed(self, request: HoldRequest):
        """
        Changes the state for each held node for the hold request to 'used'.

        :returns: True if all nodes marked USED, False otherwise.
        """
        def getHeldNodeIDs(req: HoldRequest) -> List[str]:
            node_ids: List[str] = []
            for data in req.nodes:
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
            node = self._getNode(node_id)
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

    def deleteHoldRequest(self, request: HoldRequest):
        """
        Delete a hold request.

        :param HoldRequest request: Object representing the hold request.
        """
        if not self._markHeldNodesAsUsed(request):
            self.log.info("Unable to delete hold request %s because "
                          "not all nodes marked as USED.", request.id)
            return

        path = self.HOLD_REQUEST_ROOT + "/" + request.id
        try:
            self.kazoo_client.delete(path, recursive=True)
        except NoNodeError:
            pass

    def lockHoldRequest(self, request: HoldRequest,
                        blocking: bool = True, timeout: Optional[int] = None):
        """
        Lock a node request.

        This will set the `lock` attribute of the request object when the
        lock is successfully acquired.

        :param request: The hold request to lock.
        :param blocking: Block until lock is obtained or return immediately.
        :param timeout: Don't wait forever to acquire the lock.
        """
        if not request.id:
            raise LockException(
                "Hold request without an ID cannot be locked: %s" % request)

        path = "%s/%s/lock" % (self.HOLD_REQUEST_ROOT, request.id)
        try:
            lock = Lock(self.kazoo_client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            raise LockException("Timeout trying to acquire lock %s" % path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            raise LockException("Did not get lock on %s" % path)

        request.lock = lock

    def unlockHoldRequest(self, request: HoldRequest):
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
                d = json.loads(event.event_data.data.decode('utf8'))
                old_request = self._cached_hold_requests.get(request_id)
                if old_request:
                    if event.event_data.stat.version <= old_request.stat\
                            .version:
                        # Don't update to older data
                        return
                    old_request.updateFromDict(d)
                    old_request.stat = event.event_data.stat
                else:
                    request = HoldRequest.fromDict(d)
                    request.id = request_id
                    request.stat = event.event_data.stat
                    self._cached_hold_requests[request_id] = request

            elif event.event_type == TreeEvent.NODE_REMOVED:
                try:
                    del self._cached_hold_requests[request_id]
                except KeyError:
                    pass
        except Exception:
            self.log.exception(
                "Exception in hold request cache update for event: %s", event)

    def submitNodeRequest(self, node_request, priority, watcher):
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
        node_request.created_time = time.time()
        data = node_request.toDict()

        path = '{}/{:0>3}-'.format(self.REQUEST_ROOT, priority)
        path = self.kazoo_client.create(path, json.dumps(data).encode('utf8'),
                                        makepath=True, sequence=True,
                                        ephemeral=True)
        reqid = path.split("/")[-1]
        node_request.id = reqid

        def callback(value, _):
            if value:
                self.updateNodeRequest(node_request, value)
            deleted = (value is None)  # data *are* none
            return watcher(node_request, priority, deleted)

        self.kazoo_client.DataWatch(path, callback)

    def getNodeRequest(self, node_request_id, nodeset=None):
        """
        Retrieve a NodeRequest from a given path in ZooKeeper.

        The serialized version of the NodeRequest doesn't contain a NodeSet, so
        we have to add this to the request manually. The nodeset provided to
        this method will be set on the NodeRequest before updating it. This
        will ensure that all nodes are updated as well.
        """

        path = f"{self.REQUEST_ROOT}/{node_request_id}"
        try:
            data, stat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        json_data = json.loads(data.decode("utf-8"))

        obj = NodeRequest.fromDict(json_data)
        if nodeset is None:
            # If no NodeSet is provided, we create one on-the-fly based on the
            # list of labels (node_types) stored in the NodeRequest's znode
            # data.
            # This is necessary as the logic in the updateNodeRequest() method
            # below will update each node "in-place" an thus, we have to ensure
            # that the NodeRequest has a valid NodeSet with all nodes available
            # in advance.
            # This is only used to return the nodes to nodepool in case
            # something went wrong and the original NodeRequest and/or NodeSet
            # objects are not available anymore.
            nodeset = NodeSet()
            for i, node_type in enumerate(json_data["node_types"]):
                node = Node(name=f"{node_type}-{i}", label=node_type)
                nodeset.addNode(node)

        obj.nodeset = nodeset
        # Using updateNodeRequest() here will ensure that the nodes are also
        # updated. Doing the update in here directly rather than calling it
        # from the outside afterwards, saves us one call to ZooKeeper as the
        # data we just retrieved can directly be reused.
        self.updateNodeRequest(obj, data)
        obj.id = node_request_id
        obj.stat = stat
        return obj

    def deleteNodeRequest(self, node_request):
        """
        Delete a request for nodes.

        :param NodeRequest node_request: A NodeRequest with the
            contents of the request.
        """
        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        try:
            self.kazoo_client.delete(path)
        except NoNodeError:
            pass

    def nodeRequestExists(self, node_request):
        """
        See if a NodeRequest exists in ZooKeeper.

        :param NodeRequest node_request: A NodeRequest to verify.

        :returns: True if the request exists, False otherwise.
        """
        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        if self.kazoo_client.exists(path):
            return True
        return False

    def storeNodeRequest(self, node_request):
        """
        Store the node request.

        The request is expected to already exist and is updated in its
        entirety.

        :param NodeRequest node_request: The request to update.
        """
        path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
        self.kazoo_client.set(
            path, json.dumps(node_request.toDict()).encode('utf8'))

    def updateNodeRequest(self, node_request, data=None):
        """
        Refresh an existing node request.

        :param NodeRequest node_request: The request to update.
        :param dict data: The data to use; query ZK if absent.
        """
        if data is None:
            path = '%s/%s' % (self.REQUEST_ROOT, node_request.id)
            data, stat = self.kazoo_client.get(path)
        data = json.loads(data.decode('utf8'))
        request_nodes = list(node_request.nodeset.getNodes())
        for i, nodeid in enumerate(data.get('nodes', [])):
            request_nodes[i].id = nodeid
            self._updateNode(request_nodes[i])
        node_request.updateFromDict(data)

    def storeNode(self, node):
        """
        Store the node.

        The node is expected to already exist and is updated in its
        entirety.

        :param Node node: The node to update.
        """
        path = '%s/%s' % (self.NODES_ROOT, node.id)
        self.kazoo_client.set(path, json.dumps(node.toDict()).encode('utf8'))

    def _updateNode(self, node):
        """
        Refresh an existing node.

        :param Node node: The node to update.
        """
        node_path = '%s/%s' % (self.NODES_ROOT, node.id)
        node_data, node_stat = self.kazoo_client.get(node_path)
        node_data = json.loads(node_data.decode('utf8'))
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
        lock_path = '%s/%s/lock' % (self.NODES_ROOT, node.id)
        try:
            lock = Lock(self.kazoo_client, lock_path)
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
            raise LockException(f"Node {node} does not hold a lock")
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
        path = "%s/%s" % (self.REQUEST_LOCK_ROOT, request.id)
        lock = Lock(self.kazoo_client, path)
        try:
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
        identifier = " ".join(autohold_key)
        try:
            nodes = self.kazoo_client.get_children(self.NODES_ROOT)
        except NoNodeError:
            return 0

        count = 0
        for nodeid in nodes:
            node_path = '%s/%s' % (self.NODES_ROOT, nodeid)
            try:
                node_data, node_stat = self.kazoo_client.get(node_path)
            except NoNodeError:
                # Node got removed on us. Just ignore.
                continue

            if not node_data:
                self.log.warning("Node ID %s has no data", nodeid)
                continue
            node_data = json.loads(node_data.decode('utf8'))
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
