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
from typing import TYPE_CHECKING

from kazoo.exceptions import NoNodeError, LockTimeout
from kazoo.recipe.lock import Lock

import zuul.model
from zuul.zk.exceptions import LockException


class ZooKeeperNodepoolMixin:
    NODE_ROOT = "/nodepool/nodes"
    LAUNCHER_ROOT = "/nodepool/launchers"

    def _bytesToDict(self, data):
        return json.loads(data.decode('utf8'))

    def _launcherPath(self, launcher):
        return "%s/%s" % (self.LAUNCHER_ROOT, launcher)

    def _nodePath(self, node):
        return "%s/%s" % (self.NODE_ROOT, node)

    def getRegisteredLaunchers(self):
        """
        Get a list of all launchers that have registered with ZooKeeper.

        :returns: A list of Launcher objects, or empty list if none are found.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        try:
            launcher_ids = self.client.get_children(self.LAUNCHER_ROOT)
        except NoNodeError:
            return []

        objs = []
        for launcher in launcher_ids:
            path = self._launcherPath(launcher)
            try:
                data, _ = self.client.get(path)
            except NoNodeError:
                # launcher disappeared
                continue

            objs.append(Launcher.fromDict(self._bytesToDict(data)))
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
            return self.client.get_children(self.NODE_ROOT)
        except NoNodeError:
            return []

    def getNode(self, node):
        """
        Get the data for a specific node.

        :param str node: The node ID.

        :returns: The node data, or None if the node was not found.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        path = self._nodePath(node)
        try:
            data, stat = self.client.get(path)
        except NoNodeError:
            return None
        if not data:
            return None

        d = self._bytesToDict(data)
        d['id'] = node
        return d

    def nodeIterator(self):
        """
        Utility generator method for iterating through all nodes.
        """
        for node_id in self.getNodes():
            node = self.getNode(node_id)
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

    def _markHeldNodesAsUsed(self,
                             request: zuul.model.HoldRequest):
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

        if not self._markHeldNodesAsUsed(request):
            self.log.info("Unable to delete hold request %s because "
                          "not all nodes marked as USED.", request.id)
            return

        path = self.HOLD_REQUEST_ROOT + "/" + request.id
        try:
            self.client.delete(path, recursive=True)
        except NoNodeError:
            pass

    def lockHoldRequest(self, request: zuul.model.HoldRequest,
                        blocking: bool=True, timeout: bool=None):
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
