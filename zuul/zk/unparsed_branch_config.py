# Copyright 2020 BMW Group
#
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

from typing import Optional, TYPE_CHECKING, Callable

from kazoo.exceptions import NoNodeError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import ReadLock, WriteLock


class ZooKeeperUnparsedBranchConfigMixin:

    def getLayoutHash(self, tenant: str) -> Optional[str]:
        """
        Get tenant's layout version.

        A layout version is a hash over all relevant files for the given
        tenant.

        :param tenant: Tentant
        :return: Tenant's layout relevant files hash
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
            if TYPE_CHECKING:  # IDE type checking support
                from zuul.zk import ZooKeeper
                assert isinstance(self, ZooKeeper)

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
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        lock_node = self._getZuulNodePath('config')
        return self.client.WriteLock(lock_node) if self.client else None

    def getConfigWriteLock(self) -> Optional[WriteLock]:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

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
                    except NoNodeError:
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
