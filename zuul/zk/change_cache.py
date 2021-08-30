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

import abc
import contextlib
import json
import logging
import time
import uuid
from collections.abc import Iterable
from urllib.parse import quote_plus, unquote_plus

from kazoo.exceptions import BadVersionError, NodeExistsError, NoNodeError

from zuul import model
from zuul.zk import sharding, ZooKeeperSimpleBase
from zuul.zk.exceptions import ZuulZooKeeperException
from zuul.zk.vendor.watchers import ExistingDataWatch

CHANGE_CACHE_ROOT = "/zuul/cache/connection"


def _keyFromPath(path):
    return unquote_plus(path.rpartition("/")[-1])


class ConcurrentUpdateError(ZuulZooKeeperException):
    pass


class AbstractChangeCache(ZooKeeperSimpleBase, Iterable, abc.ABC):
    """Abstract class for caching change items in Zookeeper.

    In order to make updates atomic the change data is stored separate
    from the cache entry. The data uses a random UUID znode that is
    then referenced from the actual cache entry.

    The change data is immutable, which means that an update of a cached
    item will result in a new data node. The cache entry will then be
    changed to reference the new data.

    This approach also allows us to check if a given change is
    up-to-date by comparing the referenced UUID in Zookeeper with the
    one in the local cache without loading the whole change data.

    The change data is stored in the following Zookeeper path:

        /zuul/cache/connection/<connection-name>/data/<uuid>

    The cache entries that reference the change data use the following
    path:

        /zuul/cache/connection/<connection-name>/cache/<key>

    Data nodes will not be directly removed when an entry is removed
    or updated in order to prevent race conditions with multiple
    consumers of the cache. The stale data nodes will be instead
    cleaned up in the cache's cleanup() method. This is expected to
    happen periodically.
    """
    log = logging.getLogger("zuul.zk.AbstractChangeCache")

    def __init__(self, client, connection):
        super().__init__(client)
        self.connection = connection
        self.root_path = f"{CHANGE_CACHE_ROOT}/{connection.connection_name}"
        self.cache_root = f"{self.root_path}/cache"
        self.data_root = f"{self.root_path}/data"
        self.kazoo_client.ensure_path(self.data_root)
        self.kazoo_client.ensure_path(self.cache_root)
        self._change_cache = {}
        # Data UUIDs that are candidates to be removed on the next
        # cleanup iteration.
        self._data_cleanup_candidates = set()
        self.kazoo_client.ChildrenWatch(self.cache_root, self._cacheWatcher)

    def _dataPath(self, data_uuid):
        return f"{self.data_root}/{data_uuid}"

    def _cachePath(self, key):
        return f"{self.cache_root}/{quote_plus(key)}"

    def _cacheWatcher(self, cache_keys):
        cache_keys = {unquote_plus(k) for k in cache_keys}
        existing_keys = set(self._change_cache.keys())
        deleted_keys = existing_keys - cache_keys
        for key in deleted_keys:
            with contextlib.suppress(KeyError):
                del self._change_cache[key]
        new_keys = set(cache_keys) - existing_keys
        for quoted_key in new_keys:
            self.get(unquote_plus(quoted_key))
            ExistingDataWatch(self.kazoo_client,
                              f"{self.cache_root}/{quoted_key}",
                              self._cacheItemWatcher)

    def _cacheItemWatcher(self, data, zstat, event=None):
        if not all((data, zstat, event)):
            return

        key = _keyFromPath(event.path)
        data_uuid = data.decode("utf8")
        self._get(key, data_uuid, zstat)

    def prune(self, relevant, max_age=3600):  # 1h
        cutoff_time = time.time() - max_age
        outdated = {c.cache_stat.key for c in list(self._change_cache.values())
                    if c.cache_stat.last_modified < cutoff_time}
        to_prune = outdated - set(relevant)
        for key in to_prune:
            self.delete(key)

    def cleanup(self):
        valid_uuids = {c.cache_stat.uuid
                       for c in list(self._change_cache.values())}
        stale_uuids = self._data_cleanup_candidates - valid_uuids
        for data_uuid in stale_uuids:
            self.kazoo_client.delete(self._dataPath(data_uuid), recursive=True)

        data_uuids = set(self.kazoo_client.get_children(self.data_root))
        self._data_cleanup_candidates = data_uuids - valid_uuids

    def __iter__(self):
        try:
            children = self.kazoo_client.get_children(self.cache_root)
        except NoNodeError:
            return

        for key in sorted(unquote_plus(c) for c in children):
            change = self.get(key)
            if change is not None:
                yield change

    def get(self, key):
        cache_path = self._cachePath(key)
        try:
            value, zstat = self.kazoo_client.get(cache_path)
        except NoNodeError:
            return None

        data_uuid = value.decode("utf8")
        return self._get(key, data_uuid, zstat)

    def _get(self, key, data_uuid, zstat):
        change = self._change_cache.get(key)
        if change and change.cache_stat.uuid == data_uuid:
            # Change in our local cache is up-to-date
            return change

        try:
            data = self._getData(data_uuid)
        except NoNodeError:
            cache_path = self._cachePath(key)
            self.log.error("Removing cache entry %s without any data",
                           cache_path)
            # TODO: handle no node + version mismatch
            self.kazoo_client.delete(cache_path, zstat.version)
            return None

        cache_stat = model.CacheStat(key, data_uuid, zstat.version,
                                     zstat.last_modified)
        if change:
            self._updateChange(change, data)
        else:
            change = self._changeFromData(data)

        change.cache_stat = cache_stat
        # Use setdefault here so we only have a single instance of a change
        # around. In case of a concurrent get this might return a different
        # change instance than the one we just created.
        return self._change_cache.setdefault(key, change)

    def _getData(self, data_uuid):
        with sharding.BufferedShardReader(
                self.kazoo_client, self._dataPath(data_uuid)) as stream:
            data = stream.read()
        return json.loads(data)

    def set(self, key, change):
        data_uuid = self._setData(self._dataFromChange(change))
        cache_path = self._cachePath(key)
        try:
            if change.cache_version == -1:
                self.kazoo_client.create(cache_path, data_uuid.encode("utf8"))
                version = 0
                last_modified = time.time()
            else:
                zstat = self.kazoo_client.set(
                    cache_path, data_uuid.encode("utf8"), change.cache_version)
                version = zstat.version
                last_modified = zstat.last_modified
        except (BadVersionError, NodeExistsError, NoNodeError) as exc:
            raise ConcurrentUpdateError from exc

        change.cache_stat = model.CacheStat(key, data_uuid, version,
                                            last_modified)
        self._change_cache[key] = change

    def _setData(self, data):
        data_uuid = uuid.uuid4().hex
        payload = json.dumps(data).encode("utf8")
        with sharding.BufferedShardWriter(
                self.kazoo_client, self._dataPath(data_uuid)) as stream:
            stream.write(payload)
        return data_uuid

    def delete(self, key):
        cache_path = self._cachePath(key)
        # Only delete the cache entry and NOT the data node in order to
        # prevent race conditions with other consumers. The stale data
        # nodes will be removed by the periodic cleanup.
        self.kazoo_client.delete(cache_path, recursive=True)

        with contextlib.suppress(KeyError):
            del self._change_cache[key]

    def _changeFromData(self, data):
        change_type, change_data = data["change_type"], data["change_data"]
        change_class = self._getChangeClass(change_type)
        project = self.connection.source.getProject(change_data["project"])
        change = change_class(project)
        change.deserialize(change_data)
        return change

    def _dataFromChange(self, change):
        return {
            "change_type": self._getChangeType(change),
            "change_data": change.serialize(),
        }

    def _updateChange(self, change, data):
        change.deserialize(data["change_data"])

    @abc.abstractmethod
    def _getChangeClass(self, change_type):
        """Return the change class for the given type."""
        pass

    @abc.abstractmethod
    def _getChangeType(self, change):
        """Return the change type as a string for the given type."""
        pass
