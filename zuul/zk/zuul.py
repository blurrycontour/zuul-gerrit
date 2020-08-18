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

from typing import TYPE_CHECKING, Callable, List, Optional

from kazoo.exceptions import LockTimeout
from kazoo.recipe.lock import Lock


class ZooKeeperZuulMixin:
    ZUUL_CONFIG_ROOT = "/zuul"
    # Node content max size: keep ~100kB as a reserve form the 1MB limit
    ZUUL_CONFIG_MAX_SIZE = 1024 * 1024 - 100 * 1024

    def _getZuulNodePath(self, *args: str) -> str:
        return "/".join(filter(lambda s: s is not None and s != '',
                               [self.ZUUL_CONFIG_ROOT] + list(args)))

    def _getConfigPartContent(self, parent, child) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        node = "%s/%s" % (parent, child)
        return self.client.get(node)[0].decode(encoding='UTF-8') \
            if self.client and self.client.exists(node) else ''

    def _getZuulEventConnectionPath(self, connection_name: str,
                                    path: str, sequence: Optional[str]=None):
        return self._getZuulNodePath('events', 'connection',
                                     connection_name, path, sequence or '')

    def acquireLock(self, lock: Lock, keep_locked: bool=False):
        """
        Acquires a ZK lock.

        Acquiring the ZK lock is wrapped with a threading lock. There are 2
        reasons for this "locking" lock:

        1) in production to prevent simultaneous acquisition of ZK locks
           from different threads, which may fail,
        2) in tests to prevent events being popped or pushed while waiting
           for scheduler to settle.

        The parameter keep_locked should be only set to True in the waiting
        to settle. This will allow multiple entry and lock of different
        connection in one scheduler instance from test thread and at the same
        time block lock request from runtime threads.
        If set to True, the lockingLock needs to be unlocked manually
        afterwards.

        :param lock: ZK lock to acquire
        :param keep_locked: Whether to keep the locking (threading) lock locked
        """

        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not keep_locked or not self.lockingLock.locked():
            self.lockingLock.acquire()
        locked = False
        try:
            while not locked:
                try:  # Make sure request does not hang
                    lock.acquire(timeout=10.0)
                    locked = True
                except LockTimeout:
                    self.log.debug("Could not acquire lock %s" % lock.path)
                    raise
        finally:
            if not keep_locked and self.lockingLock.locked():
                self.lockingLock.release()

    def watch_node_children(self, path: str,
                            callback: Callable[[List[str]], None]) -> None:
        """
        Watches a node for children changes.

        :param path: Node path
        :param callback: Callback
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if path not in self.node_watchers:
            self.node_watchers[path] = [callback]

            if not self.client:
                raise Exception("No zookeeper client!")

            self.client.ensure_path(path)

            def watch_children(children):
                if TYPE_CHECKING:  # IDE type checking support
                    from zuul.zk import ZooKeeper
                    assert isinstance(self, ZooKeeper)

                if len(children) > 0 and self.node_watchers[path]:
                    for watcher in self.node_watchers[path]:
                        watcher(children)

            self.client.ChildrenWatch(path, watch_children)
        else:
            self.node_watchers[path].append(callback)

    def unwatch_node_children_completely(self, path: str) -> None:
        """
        Removes all children watches for the given path.
        :param path: Node path
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if path in self.node_watchers:
            self.node_watchers[path].clear()
