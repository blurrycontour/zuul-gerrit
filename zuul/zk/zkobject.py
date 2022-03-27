# Copyright 2021 Acme Gating, LLC
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
import time
import types
import zlib

from kazoo.exceptions import NodeExistsError, NoNodeError
from kazoo.retry import KazooRetry

from zuul.zk import sharding
from zuul.zk import ZooKeeperClient


class ZKContext:
    def __init__(self, zk_client, lock, stop_event, log):
        if isinstance(zk_client, ZooKeeperClient):
            client = zk_client.client
        else:
            client = zk_client
        self.client = client
        self.lock = lock
        self.stop_event = stop_event
        self.log = log
        self.cumulative_read_time = 0.0
        self.cumulative_write_time = 0.0
        self.cumulative_read_objects = 0
        self.cumulative_write_objects = 0
        self.cumulative_read_znodes = 0
        self.cumulative_write_znodes = 0
        self.cumulative_read_bytes = 0
        self.cumulative_write_bytes = 0

    def sessionIsValid(self):
        return ((not self.lock or self.lock.is_still_valid()) and
                (not self.stop_event or not self.stop_event.is_set()))

    def sessionIsInvalid(self):
        return not self.sessionIsValid()

    def updateStatsFromOtherContext(self, other):
        self.cumulative_read_time += other.cumulative_read_time
        self.cumulative_write_time += other.cumulative_write_time
        self.cumulative_read_objects += other.cumulative_read_objects
        self.cumulative_write_objects += other.cumulative_write_objects
        self.cumulative_read_znodes += other.cumulative_read_znodes
        self.cumulative_write_znodes += other.cumulative_write_znodes
        self.cumulative_read_bytes += other.cumulative_read_bytes
        self.cumulative_write_bytes += other.cumulative_write_bytes


class LocalZKContext:
    """A Local ZKContext that means don't actually write anything to ZK"""

    def __init__(self, log):
        self.client = None
        self.lock = None
        self.stop_event = None
        self.log = log

    def sessionIsValid(self):
        return True

    def sessionIsInvalid(self):
        return False


class ZKObject:
    _retry_interval = 5
    _zkobject_compressed_size = 0
    _zkobject_uncompressed_size = 0

    # Implementations of these two methods are required
    def getPath(self):
        """Return the path to save this object in ZK

        :returns: A string representation of the Znode path
        """
        raise NotImplementedError()

    def serialize(self, context):
        """Implement this method to return the data to save in ZK.

        :returns: A byte string
        """
        raise NotImplementedError()

    # This should work for most classes
    def deserialize(self, data, context):
        """Implement this method to convert serialized data into object
        attributes.

        :param bytes data: A byte string to deserialize
        :param ZKContext context: A ZKContext object with the current
            ZK session and lock.

        :returns: A dictionary of attributes and values to be set on
        the object.
        """
        return json.loads(data.decode('utf-8'))

    # These methods are public and shouldn't need to be overridden
    def updateAttributes(self, context, **kw):
        """Update attributes on this object and save to ZooKeeper

        Instead of using attribute assignment, call this method to
        update attributes on this object.  It will update the local
        values and also write out the updated object to ZooKeeper.

        :param ZKContext context: A ZKContext object with the current
            ZK session and lock.  Be sure to acquire the lock before
            calling methods on this object.  This object will validate
            that the lock is still valid before writing to ZooKeeper.

        All other parameters are keyword arguments which are
        attributes to be set.  Set as many attributes in one method
        call as possible for efficient network use.
        """
        old = self.__dict__.copy()
        self._set(**kw)
        serial = self._trySerialize(context)
        if hash(serial) != getattr(self, '_zkobject_hash', None):
            try:
                self._save(context, serial)
            except Exception:
                # Roll back our old values if we aren't able to update ZK.
                self._set(**old)
                raise

    @contextlib.contextmanager
    def activeContext(self, context):
        if self._active_context:
            raise RuntimeError(
                f"Another context is already active {self._active_context}")
        try:
            old = self.__dict__.copy()
            self._set(_active_context=context)
            yield
            serial = self._trySerialize(context)
            if hash(serial) != getattr(self, '_zkobject_hash', None):
                try:
                    self._save(context, serial)
                except Exception:
                    # Roll back our old values if we aren't able to update ZK.
                    self._set(**old)
                    raise
        finally:
            self._set(_active_context=None)

    @classmethod
    def new(klass, context, **kw):
        """Create a new instance and save it in ZooKeeper"""
        obj = klass()
        obj._set(**kw)
        data = obj._trySerialize(context)
        obj._save(context, data, create=True)
        return obj

    @classmethod
    def fromZK(klass, context, path, **kw):
        """Instantiate a new object from data in ZK"""
        obj = klass()
        obj._set(**kw)
        obj._load(context, path=path)
        return obj

    def refresh(self, context):
        """Update data from ZK"""
        self._load(context)

    def _trySerialize(self, context):
        if isinstance(context, LocalZKContext):
            return b''
        try:
            return self.serialize(context)
        except Exception:
            # A higher level must handle this exception, but log
            # ourself here so we know what object triggered it.
            context.log.error(
                "Exception serializing ZKObject %s", self)
            raise

    def delete(self, context):
        path = self.getPath()
        if context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        try:
            self._retry(context, context.client.delete,
                        path, recursive=True)
            return
        except Exception:
            context.log.error(
                "Exception deleting ZKObject %s at %s", self, path)
            raise

    def estimateDataSize(self, seen=None):
        """Attempt to find all ZKObjects below this one and sum their
        compressed and uncompressed sizes.

        :returns: (compressed_size, uncompressed_size)
        """
        compressed_size = self._zkobject_compressed_size
        uncompressed_size = self._zkobject_uncompressed_size

        if seen is None:
            seen = {self}

        def walk(obj):
            compressed = 0
            uncompressed = 0
            if isinstance(obj, ZKObject):
                if obj in seen:
                    return 0, 0
                seen.add(obj)
                compressed, uncompressed = obj.estimateDataSize(seen)
            elif (isinstance(obj, dict) or
                  isinstance(obj, types.MappingProxyType)):
                for sub in obj.values():
                    c, u = walk(sub)
                    compressed += c
                    uncompressed += u
            elif (isinstance(obj, list) or
                  isinstance(obj, tuple)):
                for sub in obj:
                    c, u = walk(sub)
                    compressed += c
                    uncompressed += u
            return compressed, uncompressed

        c, u = walk(self.__dict__)
        compressed_size += c
        uncompressed_size += u

        return (compressed_size, uncompressed_size)

    # Private methods below

    def _retry(self, context, func, *args, max_tries=-1, **kw):
        kazoo_retry = KazooRetry(max_tries=max_tries,
                                 interrupt=context.sessionIsInvalid,
                                 delay=self._retry_interval, backoff=0,
                                 ignore_expire=False)
        try:
            return kazoo_retry(func, *args, **kw)
        except InterruptedError:
            pass

    def __init__(self):
        # Don't support any arguments in constructor to force us to go
        # through a save or restore path.
        super().__init__()
        self._set(_active_context=None)

    @staticmethod
    def _retryableLoad(context, path):
        start = time.perf_counter()
        compressed_data, zstat = context.client.get(path)
        context.cumulative_read_time += time.perf_counter() - start
        context.cumulative_read_objects += 1
        context.cumulative_read_znodes += 1
        context.cumulative_read_bytes += len(compressed_data)
        return compressed_data, zstat

    def _load(self, context, path=None):
        if path is None:
            path = self.getPath()
        if context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        try:
            compressed_data, zstat = self._retry(context, self._retryableLoad,
                                                 context, path)
        except Exception:
            context.log.error(
                "Exception loading ZKObject %s at %s", self, path)
            raise
        self._set(_zkobject_hash=None)
        try:
            data = zlib.decompress(compressed_data)
        except zlib.error:
            # Fallback for old, uncompressed data
            data = compressed_data
        self._set(**self.deserialize(data, context))
        self._set(_zstat=zstat,
                  _zkobject_hash=hash(data),
                  _zkobject_compressed_size=len(compressed_data),
                  _zkobject_uncompressed_size=len(data),
                  )

    @staticmethod
    def _retryableSave(context, create, path, compressed_data, version):
        start = time.perf_counter()
        if create:
            real_path, zstat = context.client.create(
                path, compressed_data, makepath=True,
                include_data=True)
        else:
            zstat = context.client.set(path, compressed_data,
                                       version=version)
        context.cumulative_write_time += time.perf_counter() - start
        context.cumulative_write_objects += 1
        context.cumulative_write_znodes += 1
        context.cumulative_write_bytes += len(compressed_data)
        return zstat

    def _save(self, context, data, create=False):
        if isinstance(context, LocalZKContext):
            return
        path = self.getPath()
        if context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        compressed_data = zlib.compress(data)

        try:
            if hasattr(self, '_zstat'):
                version = self._zstat.version
            else:
                version = None
            zstat = self._retry(context, self._retryableSave,
                                context, create, path, compressed_data,
                                version)
        except Exception:
            context.log.error(
                "Exception saving ZKObject %s at %s", self, path)
            raise
        self._set(_zstat=zstat,
                  _zkobject_hash=hash(data),
                  _zkobject_compressed_size=len(compressed_data),
                  _zkobject_uncompressed_size=len(data),
                  )

    def __setattr__(self, name, value):
        if self._active_context:
            super().__setattr__(name, value)
        else:
            raise Exception("Unable to modify ZKObject %s" %
                            (repr(self),))

    def _set(self, **kw):
        for name, value in kw.items():
            super().__setattr__(name, value)


class ShardedZKObject(ZKObject):
    # If the node exists when we create we normally error, unless this
    # is set, in which case we proceed and truncate.
    truncate_on_create = False
    # Normally we delete nodes which have syntax errors, but the
    # pipeline summary is read without a write lock, so those are
    # expected.  Don't delete them in that case.
    delete_on_error = True

    @staticmethod
    def _retryableLoad(context, path):
        with sharding.BufferedShardReader(context.client, path) as stream:
            data = stream.read()
            compressed_size = stream.compressed_bytes_read
            context.cumulative_read_time += stream.cumulative_read_time
            context.cumulative_read_objects += 1
            context.cumulative_read_znodes += stream.znodes_read
            context.cumulative_read_bytes += compressed_size
        if not data and context.client.exists(path) is None:
            raise NoNodeError
        return data, compressed_size

    def _load(self, context, path=None):
        if path is None:
            path = self.getPath()
        if context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        try:
            self._set(_zkobject_hash=None)
            data, compressed_size = self._retry(context, self._retryableLoad,
                                                context, path)
            self._set(**self.deserialize(data, context))
            self._set(_zkobject_hash=hash(data),
                      _zkobject_compressed_size=compressed_size,
                      _zkobject_uncompressed_size=len(data),
                      )
        except Exception:
            # A higher level must handle this exception, but log
            # ourself here so we know what object triggered it.
            context.log.error(
                "Exception loading ZKObject %s at %s", self, path)
            if self.delete_on_error:
                self.delete(context)
            raise

    @staticmethod
    def _retryableSave(context, path, data):
        with sharding.BufferedShardWriter(context.client, path) as stream:
            stream.truncate(0)
            stream.write(data)
            stream.flush()
            compressed_size = stream.compressed_bytes_written
            context.cumulative_write_time += stream.cumulative_write_time
            context.cumulative_write_objects += 1
            context.cumulative_write_znodes += stream.znodes_written
            context.cumulative_write_bytes += compressed_size
        return compressed_size

    def _save(self, context, data, create=False):
        if isinstance(context, LocalZKContext):
            return
        path = self.getPath()
        if context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        try:
            if create and not self.truncate_on_create:
                exists = self._retry(context, context.client.exists, path)
                if exists is not None:
                    raise NodeExistsError
            compressed_size = self._retry(context, self._retryableSave,
                                          context, path, data)
            self._set(_zkobject_hash=hash(data),
                      _zkobject_compressed_size=compressed_size,
                      _zkobject_uncompressed_size=len(data),
                      )
        except Exception:
            context.log.error(
                "Exception saving ZKObject %s at %s", self, path)
            raise
