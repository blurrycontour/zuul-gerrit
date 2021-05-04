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
import json
import logging

from collections.abc import MutableMapping
from urllib.parse import quote_plus, unquote_plus

from kazoo.exceptions import NoNodeError

from zuul.zk import sharding, ZooKeeperSimpleBase


def _safe_path(root_path, *keys):
    return "/".join((root_path, *(quote_plus(k) for k in keys)))


class FilesCache(ZooKeeperSimpleBase, MutableMapping):
    """Cache of raw config files in Zookeeper for a project-branch.

    Data will be stored in Zookeeper using the following path:
        /zuul/config/<project>/<branch>/<filename>

    """
    log = logging.getLogger("zuul.zk.config_cache.FilesCache")

    def __init__(self, client, root_path):
        super().__init__(client)
        self.root_path = root_path
        self.files_path = f"{root_path}/files"

    def setValidFor(self, extra_config_files, extra_config_dirs):
        """Set the cache valid for the given extra config files/dirs."""
        data = {
            "extra_files_searched": list(extra_config_files),
            "extra_dirs_searched": list(extra_config_dirs),
        }
        payload = json.dumps(data).encode("utf8")
        try:
            self.kazoo_client.set(self.root_path, payload)
        except NoNodeError:
            self.kazoo_client.create(self.root_path, payload, makepath=True)

    def isValidFor(self, tpc, cache_ltime):
        """Check if the cache is valid.

        Check if the cache is valid for the given tenant project config
        (tpc) and that it is up-to-date, relative to the give logical
        timestamp.

        """
        try:
            data, zstat = self.kazoo_client.get(self.root_path)
        except NoNodeError:
            return False

        if zstat.last_modified_transaction_id < cache_ltime:
            # Cache is outdated
            return False

        try:
            content = json.loads(data)
            extra_files_searched = set(content["extra_files_searched"])
            extra_dirs_searched = set(content["extra_dirs_searched"])
        except Exception:
            return False

        return (set(tpc.extra_config_files) <= extra_files_searched
                and set(tpc.extra_config_dirs) <= extra_dirs_searched)

    def _key_path(self, key):
        return _safe_path(self.files_path, key)

    def __getitem__(self, key):
        try:
            with sharding.BufferedShardReader(
                self.kazoo_client, self._key_path(key)
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
        try:
            children = self.kazoo_client.get_children(self.files_path)
        except NoNodeError:
            children = []
        yield from sorted(unquote_plus(c) for c in children)

    def __len__(self):
        try:
            children = self.kazoo_client.get_children(self.files_path)
        except NoNodeError:
            children = []
        return len(children)


class UnparsedConfigCache(ZooKeeperSimpleBase):
    """Zookeeper cache for unparsed config files."""

    CONFIG_ROOT = "/zuul/config"
    log = logging.getLogger("zuul.zk.config_cache.UnparsedConfigCache")

    def __init__(self, client):
        super().__init__(client)
        self.cache_path = f"{self.CONFIG_ROOT}/cache"
        self.lock_path = f"{self.CONFIG_ROOT}/lock"

    def readLock(self, project_cname):
        return self.kazoo_client.ReadLock(
            _safe_path(self.lock_path, project_cname))

    def writeLock(self, project_cname):
        return self.kazoo_client.WriteLock(
            _safe_path(self.lock_path, project_cname))

    def getFilesCache(self, project_cname, branch_name):
        path = _safe_path(self.cache_path, project_cname, branch_name)
        return FilesCache(self.client, path)

    def listCachedProjects(self):
        try:
            children = self.kazoo_client.get_children(self.cache_path)
        except NoNodeError:
            children = []
        yield from sorted(unquote_plus(c) for c in children)

    def clearCache(self, project_cname, branch_name=None):
        if branch_name is None:
            path = _safe_path(self.cache_path, project_cname)
        else:
            path = _safe_path(self.cache_path, project_cname, branch_name)
        with contextlib.suppress(NoNodeError):
            self.kazoo_client.delete(path, recursive=True)
