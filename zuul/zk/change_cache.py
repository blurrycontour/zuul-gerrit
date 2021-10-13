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
import threading
import time
import uuid
import hashlib
from collections import defaultdict
from collections.abc import Iterable

from kazoo.exceptions import BadVersionError, NodeExistsError, NoNodeError

from zuul import model
from zuul.zk import sharding, ZooKeeperSimpleBase
from zuul.zk.exceptions import ZuulZooKeeperException
from zuul.zk.vendor.watchers import ExistingDataWatch

CHANGE_CACHE_ROOT = "/zuul/cache/connection"


class ConcurrentUpdateError(ZuulZooKeeperException):
    pass


def str_or_none(d):
    if d is None:
        return d
    return str(d)


class ChangeKey:
    """Represents a change key

    This is used to look up a change in the change cache.

    It also contains enough basic information about a change in order
    to determine if two entries in the change cache are related or
    identical.

    There are two ways to refer to a Change in ZK.  If one ZK object
    refers to a change, it should use ChangeKey.reference.  This is a
    dictionary with structured information about the change.  The
    contents can be used to construct a ChangeKey, and that can be
    used to pull the Change from the cache.

    The cache itself uses a sha256 digest of the reference as the
    actual cache key in ZK.  This reduces and stabilizes the length of
    the cache keys themselves.  Methods outside of the change_cache
    should not use this directly.

    """

    def __init__(self, connection_name, project_name,
                 change_type, stable_id, revision):
        self.connection_name = str_or_none(connection_name)
        self.project_name = str_or_none(project_name)
        self.change_type = str_or_none(change_type)
        self.stable_id = str_or_none(stable_id)
        self.revision = str_or_none(revision)

        reference = dict(
            connection_name=connection_name,
            project_name=project_name,
            change_type=change_type,
            stable_id=stable_id,
            revision=revision,
        )

        self.reference = json.dumps(reference)
        msg = self.reference.encode('utf8')
        self._hash = hashlib.sha256(msg).hexdigest()

    def __hash__(self):
        return hash(self.reference)

    def __eq__(self, other):
        return (isinstance(other, ChangeKey) and
                self.reference == other.reference)

    @classmethod
    def fromReference(cls, data):
        data = json.loads(data)
        return cls(data['connection_name'], data['project_name'],
                   data['change_type'], data['stable_id'], data['revision'])

    def isSameChange(self, other):
        return all([
            self.connection_name == str_or_none(other.connection_name),
            self.project_name == str_or_none(other.project_name),
            self.change_type == str_or_none(other.change_type),
            self.stable_id == str_or_none(other.stable_id),
        ])


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
        # Per change locks to serialize concurrent creation and update of
        # local objects.
        self._change_locks = defaultdict(threading.Lock)
        self._watched_keys = set()
        # Data UUIDs that are candidates to be removed on the next
        # cleanup iteration.
        self._data_cleanup_candidates = set()
        self.kazoo_client.ChildrenWatch(self.cache_root, self._cacheWatcher)

    def _dataPath(self, data_uuid):
        return f"{self.data_root}/{data_uuid}"

    def _cachePath(self, key_hash):
        return f"{self.cache_root}/{key_hash}"

    def _cacheWatcher(self, cache_keys):
        # This method deals with key hashes exclusively
        cache_keys = set(cache_keys)
        existing_keys = set(self._change_cache.keys())
        deleted_keys = existing_keys - cache_keys
        for key in deleted_keys:
            with contextlib.suppress(KeyError):
                del self._change_cache[key]
            with contextlib.suppress(KeyError):
                del self._change_locks[key]

        stale_watches = self._watched_keys - cache_keys
        for key in stale_watches:
            with contextlib.suppress(KeyError):
                self._watched_keys.remove(key)

        new_keys = cache_keys - self._watched_keys
        for key in new_keys:
            ExistingDataWatch(self.kazoo_client,
                              f"{self.cache_root}/{key}",
                              self._cacheItemWatcher)
            self._watched_keys.add(key)

    def _cacheItemWatcher(self, data, zstat, event=None):
        if not all((data, zstat, event)):
            return

        key, data_uuid = self._loadKey(data)
        self._get(key, data_uuid, zstat)

    def _loadKey(self, data):
        data = json.loads(data.decode("utf8"))
        key = ChangeKey.fromReference(data['key_reference'])
        return key, data['data_uuid']

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

        for key_hash in children:
            change = self._get_from_key_hash(key_hash)
            if change is not None:
                yield change

    def get(self, key):
        cache_path = self._cachePath(key._hash)
        try:
            value, zstat = self.kazoo_client.get(cache_path)
        except NoNodeError:
            return None

        _, data_uuid = self._loadKey(value)
        return self._get(key, data_uuid, zstat)

    def _get_from_key_hash(self, key_hash):
        cache_path = self._cachePath(key_hash)
        try:
            value, zstat = self.kazoo_client.get(cache_path)
        except NoNodeError:
            return None

        key, data_uuid = self._loadKey(value)
        return self._get(key, data_uuid, zstat)

    def _get(self, key, data_uuid, zstat):
        change = self._change_cache.get(key._hash)
        if change and change.cache_stat.uuid == data_uuid:
            # Change in our local cache is up-to-date
            return change

        try:
            data = self._getData(data_uuid)
        except (NoNodeError, json.JSONDecodeError):
            cache_path = self._cachePath(key._hash)
            self.log.error("Removing cache entry %s without any data",
                           cache_path)
            # TODO: handle no node + version mismatch
            self.kazoo_client.delete(cache_path, zstat.version)
            return None

        with self._change_locks[key._hash]:
            if change:
                # While holding the lock check if we still need to update
                # the change and skip the update if we have the latest version.
                if change.cache_version >= zstat.version:
                    return change
                self._updateChange(change, data)
            else:
                change = self._changeFromData(data)

            change.cache_stat = model.CacheStat(key, data_uuid, zstat.version,
                                                zstat.last_modified)
            # Use setdefault here so we only have a single instance of a change
            # around. In case of a concurrent get this might return a different
            # change instance than the one we just created.
            return self._change_cache.setdefault(key._hash, change)

    def _getData(self, data_uuid):
        with sharding.BufferedShardReader(
                self.kazoo_client, self._dataPath(data_uuid)) as stream:
            data = stream.read()
        return json.loads(data)

    def set(self, key, change, version=-1):
        data_uuid = self._setData(self._dataFromChange(change))
        # Add the change_key info here mostly for debugging since the
        # hash is non-reversible.
        cache_data = json.dumps(dict(
            data_uuid=data_uuid,
            key_reference=key.reference,
        ))
        cache_path = self._cachePath(key._hash)
        with self._change_locks[key._hash]:
            try:
                if version == -1:
                    _, zstat = self.kazoo_client.create(
                        cache_path,
                        cache_data.encode("utf8"),
                        include_data=True)
                else:
                    # Sanity check that we only have a single change instance
                    # for a key.
                    if self._change_cache[key._hash] is not change:
                        raise RuntimeError(
                            "Conflicting change objects (existing "
                            f"{self._change_cache[key._hash]} vs. "
                            f"new {change} "
                            f"for key '{key.reference}'")
                    zstat = self.kazoo_client.set(
                        cache_path, cache_data.encode("utf8"), version)
            except (BadVersionError, NodeExistsError, NoNodeError) as exc:
                raise ConcurrentUpdateError from exc

            change.cache_stat = model.CacheStat(
                key, data_uuid, zstat.version, zstat.last_modified)
            self._change_cache[key._hash] = change

    def _setData(self, data):
        data_uuid = uuid.uuid4().hex
        payload = json.dumps(data).encode("utf8")
        with sharding.BufferedShardWriter(
                self.kazoo_client, self._dataPath(data_uuid)) as stream:
            stream.write(payload)
        return data_uuid

    def updateChangeWithRetry(self, key, change, update_func, retry_count=5):
        for attempt in range(1, retry_count + 1):
            try:
                version = change.cache_version
                update_func(change)
                self.set(key, change, version)
                break
            except ConcurrentUpdateError:
                self.log.info(
                    "Conflicting cache update of %s (attempt: %s/%s)",
                    change, attempt, retry_count)
                if attempt == retry_count:
                    raise
            # Update the cache and get the change as it might have
            # changed due to a concurrent create.
            change = self.get(key)
        return change

    def delete(self, key):
        cache_path = self._cachePath(key._hash)
        # Only delete the cache entry and NOT the data node in order to
        # prevent race conditions with other consumers. The stale data
        # nodes will be removed by the periodic cleanup.
        self.kazoo_client.delete(cache_path, recursive=True)

        with contextlib.suppress(KeyError):
            del self._change_cache[key._hash]

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

    def _getChangeClass(self, change_type):
        """Return the change class for the given type."""
        return self.CHANGE_TYPE_MAP[change_type]

    def _getChangeType(self, change):
        """Return the change type as a string for the given type."""
        return type(change).__name__

    @abc.abstractproperty
    def CHANGE_TYPE_MAP(self):
        """Return a mapping of change type as string to change class.

        This property cann also be defined as a class attribute.
        """
        pass
