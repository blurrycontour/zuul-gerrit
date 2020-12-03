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

import logging

from collections.abc import MutableMapping
from typing import Callable, Iterator, TypeVar
from urllib.parse import quote_plus, unquote_plus

from kazoo.exceptions import NoNodeError

from zuul.lib.collections import DefaultKeyDict
from zuul.zk import ZooKeeperClient, ZooKeeperBase
from zuul.zk.sharding import BufferedShardIO


def _key_path(root_path: str, *keys: str) -> str:
    return "/".join((root_path, *(quote_plus(k) for k in keys)))


class UnparsedFilesCache(ZooKeeperBase, MutableMapping):
    log = logging.getLogger("zuul.zk.config_cache.UnparsedFilesCache")

    def __init__(self, client: ZooKeeperClient, root_path: str):
        super().__init__(client)
        self.root_path = root_path
        self.kazoo_client.ensure_path(root_path)

    @property
    def ltime(self) -> int:
        data, _ = self.kazoo_client.get(self.root_path)
        try:
            return int(data)
        except ValueError:
            return -1

    @ltime.setter
    def ltime(self, value: int) -> None:
        self.kazoo_client.set(self.root_path, str(value).encode("utf8"))

    def _key_path(self, key: str) -> str:
        return _key_path(self.root_path, key)

    def __getitem__(self, key: str) -> str:
        try:
            with BufferedShardIO(
                self.kazoo_client, self._key_path(key)
            ) as stream:
                return stream.read()
        except NoNodeError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: str) -> None:
        path = self._key_path(key)
        self.kazoo_client.ensure_path(path)
        with BufferedShardIO(self.kazoo_client, path) as stream:
            stream.truncate()
            stream.write(value)

    def __delitem__(self, key: str) -> None:
        try:
            self.kazoo_client.delete(self._key_path(key), recursive=True)
        except NoNodeError:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        try:
            children = self.kazoo_client.get_children(self.root_path)
        except NoNodeError:
            return
        yield from sorted(unquote_plus(c) for c in children)

    def __len__(self) -> int:
        try:
            return len(self.kazoo_client.get_children(self.root_path))
        except NoNodeError:
            return 0


T = TypeVar("T")


class _ZookeeperNestedCache(ZooKeeperBase, DefaultKeyDict[T]):
    log = logging.getLogger("zuul.zk.config_cache.ZookeeperNestedCache")

    def __init__(
        self,
        client: ZooKeeperClient,
        cache_root: str,
        default_factory: Callable[[str], T],
    ):
        ZooKeeperBase.__init__(self, client)
        DefaultKeyDict.__init__(self, default_factory)
        self.cache_root = cache_root

    def __delitem__(self, key):
        super().__delitem__(key)
        self.kazoo_client.delete(
            _key_path(self.cache_root, key), recursive=True
        )


def create_unparsed_files_cache(client: ZooKeeperClient):
    CACHE_ROOT = "/zuul/config"
    return _ZookeeperNestedCache[_ZookeeperNestedCache](
        client,
        CACHE_ROOT,
        lambda t: _ZookeeperNestedCache[_ZookeeperNestedCache](
            client,
            _key_path(CACHE_ROOT, t),
            lambda p: _ZookeeperNestedCache[UnparsedFilesCache](
                client,
                _key_path(CACHE_ROOT, t, p),
                lambda b: UnparsedFilesCache(
                    client, _key_path(CACHE_ROOT, t, p, b)
                ),
            ),
        ),
    )
