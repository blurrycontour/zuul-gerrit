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

from typing import TYPE_CHECKING, Callable, List


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
