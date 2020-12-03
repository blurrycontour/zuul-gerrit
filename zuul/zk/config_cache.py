# Copyright 2021 BMW Group
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

import contextlib
import logging
import threading
import uuid

from collections.abc import MutableMapping
from urllib.parse import quote_plus, unquote_plus

from kazoo.exceptions import NoNodeError
from kazoo.recipe.cache import TreeCache

from zuul.lib.collections import DefaultKeyDict
from zuul.zk import sharding, ZooKeeperSimpleBase
from zuul.zk.exceptions import SyncTimeoutException


def _key_path(root_path, *keys):
    return "/".join((root_path, *(quote_plus(k) for k in keys)))


class FilesCache(ZooKeeperSimpleBase, MutableMapping):
    """Cache for the raw content of config files.

    Data will be stored in Zookeeper using the following path:
        /zuul/config/<tenant>/<project>/<branch>/<filename>

    In case a project branch doesn't contain any configuration, we simply
    create an empty root path to distinguish it from a project branch that
    has not been cached yet.
    """
    log = logging.getLogger("zuul.zk.config_cache.FilesCache")

    def __init__(self, client, root_path, cache):
        super().__init__(client)
        self.root_path = root_path
        self.cache = cache

    def markValid(self):
        # To mark a cache as valid we simply make sure the root path exists.
        # This is necessary for projects that don't have an in-repo config.
        self.kazoo_client.ensure_path(self.root_path)

    def isValid(self):
        # If the path exists we know that it is valid for the project-branch
        # combination.
        return self.cache.get_data(self.root_path) is not None

    def _key_path(self, key):
        return _key_path(self.root_path, key)

    def __getitem__(self, key):
        try:
            with sharding.BufferedShardReader(
                self.kazoo_client, self._key_path(key), self.cache
            ) as stream:
                return stream.read().decode("utf8")
        except NoNodeError:
            raise KeyError(key)

    def __setitem__(self, key, value):
        path = self._key_path(key)
        with sharding.BufferedShardWriter(self.kazoo_client, path) as stream:
            stream.truncate(0)
            stream.write(value.encode("utf8"))

    def __delitem__(self, key):
        try:
            self.kazoo_client.delete(self._key_path(key), recursive=True)
        except NoNodeError:
            raise KeyError(key)

    def __iter__(self):
        children = self.cache.get_children(self.root_path, default=[])
        yield from sorted(unquote_plus(c) for c in children)

    def __len__(self):
        return len(self.cache.get_children(self.root_path, default=[]))


class _NestedCache(ZooKeeperSimpleBase, DefaultKeyDict):
    """DefaultKeyDict that on delete also removes data from Zookeeper."""
    log = logging.getLogger("zuul.zk.config_cache.NestedCache")

    def __init__(self, client, cache_root, default_factory):
        ZooKeeperSimpleBase.__init__(self, client)
        DefaultKeyDict.__init__(self, default_factory)
        self.cache_root = cache_root

    def __delitem__(self, key):
        # Ignore the KeyError here as we might not have an item in our local
        # dictionary, but we always want to delete it from Zookeeper.
        with contextlib.suppress(KeyError):
            super().__delitem__(key)
        with contextlib.suppress(NoNodeError):
            self.kazoo_client.delete(_key_path(self.cache_root, key),
                                     recursive=True)


class UnparsedConfigCache(ZooKeeperSimpleBase):
    """Cache that holds the unparsed config files.

    Instances of this class own the Kazoo tree cache that is used as a data
    source for the files cache of a project branch.

    Since the access to the cache must be read-write locked on a per-tenant
    basis, we don't have to worry about concurrent modifications from multipe
    schedulers.

    The data from Zookeeper is stored internally in the tree cache and will
    directly be used for read access. The event listener however is still
    necessary to wait for the cache to be in sync.

    """
    CONFIG_ROOT = "/zuul/config"
    log = logging.getLogger("zuul.zk.config_cache.UnparsedConfigCache")

    def __init__(self, client):
        super().__init__(client)
        self.sync_root = f"{self.CONFIG_ROOT}/_sync"
        self.kazoo_client.ensure_path(self.sync_root)
        self._sync_watches = {}
        self.tree_cache = TreeCache(self.kazoo_client, self.CONFIG_ROOT)
        self.tree_cache.listen(self._onCacheEvent)
        self.tree_cache.listen_fault(self._onCacheError)
        self._cache_registry = self._createCacheRegistry()

    def _createCacheRegistry(self):
        """Create a nested files cache registry.

        Returns a nested mapping of:
          tenant_name -> project_name -> branch_name -> FilesCache

        Caches are dynamically created with the supplied ZK client as
        they are accessed via the registry.
        """
        return _NestedCache(
            self.client, self.CONFIG_ROOT,
            lambda t: _NestedCache(
                self.client, _key_path(self.CONFIG_ROOT, t),
                lambda p: _NestedCache(
                    self.client, _key_path(self.CONFIG_ROOT, t, p),
                    lambda b: FilesCache(
                        self.client, _key_path(self.CONFIG_ROOT, t, p, b),
                        self.tree_cache))))

    def _onCacheEvent(self, event):
        if event.event_data is None:
            return
        if not event.event_data.path.startswith(f"{self.sync_root}/"):
            return
        with contextlib.suppress(KeyError):
            watch = self._sync_watches[event.event_data.path]
            watch.set()

    def _onCacheError(self, exception):
        self.log.exception(exception)

    def waitForSync(self, timeout=None):
        """Wait for the cache to process outstanding events.

        To make sure the local cache is up-to-date, we create a temporary node
        and wait for it to show up in the cache.
        """
        sync_path = f"{self.sync_root}/{uuid.uuid4().hex}"
        watch = self._sync_watches[sync_path] = threading.Event()
        try:
            self.kazoo_client.create(sync_path, b"", ephemeral=True)
            if not watch.wait(timeout):
                raise SyncTimeoutException("Timeout waiting for cache to sync")
        finally:
            with contextlib.suppress(KeyError):
                del self._sync_watches[sync_path]
            with contextlib.suppress(NoNodeError):
                self.kazoo_client.delete(sync_path)

    def start(self):
        self.tree_cache.start()

    def stop(self):
        self.tree_cache.close()

    def getFilesCache(self, tenant_name, project_name, branch_name):
        return self._cache_registry[tenant_name][project_name][branch_name]

    def clearTenant(self, tenant_name):
        with contextlib.suppress(KeyError):
            del self._cache_registry[tenant_name]

    def clearProject(self, tenant_name, project_name):
        with contextlib.suppress(KeyError):
            del self._cache_registry[tenant_name][project_name]

    def clearBranch(self, tenant_name, project_name, branch_name):
        with contextlib.suppress(KeyError):
            del self._cache_registry[tenant_name][project_name][branch_name]
