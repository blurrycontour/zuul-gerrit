# Copyright 2020 BMW Group
# Copyright 2022 Acme Gating, LLC
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

import hashlib

from kazoo.exceptions import NoNodeError
from kazoo.retry import KazooRetry

from zuul.zk.locks import locked, SessionAwareLock
from zuul.zk.zkobject import LocalZKContext, ZKContext
from zuul.zk import sharding


class BlobStore:
    _retry_interval = 5
    data_root = "/zuul/cache/blob/data"
    lock_root = "/zuul/cache/blob/lock"

    def __init__(self, context):
        self.context = context

    def _getRootPath(self, key):
        return f"{self.data_root}/{key[0:2]}/{key}"

    def _getPath(self, key):
        root = self._getRootPath(key)
        return f"{root}/data"

    def _getFlagPath(self, key):
        root = self._getRootPath(key)
        return f"{root}/complete"

    def _retry(self, context, func, *args, max_tries=-1, **kw):
        kazoo_retry = KazooRetry(max_tries=max_tries,
                                 interrupt=context.sessionIsInvalid,
                                 delay=self._retry_interval, backoff=0,
                                 ignore_expire=False)
        try:
            return kazoo_retry(func, *args, **kw)
        except InterruptedError:
            pass

    @staticmethod
    def _retryableLoad(context, key, path, flag):
        if not context.client.exists(flag):
            raise KeyError(key)
        with sharding.BufferedShardReader(context.client, path) as stream:
            data = stream.read()
            compressed_size = stream.compressed_bytes_read
            context.cumulative_read_time += stream.cumulative_read_time
            context.cumulative_read_objects += 1
            context.cumulative_read_znodes += stream.znodes_read
            context.cumulative_read_bytes += compressed_size
        return data, compressed_size

    def get(self, key):
        path = self._getPath(key)
        flag = self._getFlagPath(key)

        if self.context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")

        data, compressed_size = self._retry(self.context, self._retryableLoad,
                                            self.context, key, path, flag)
        return data

    def _checkKey(self, key):
        # This returns whether the key is in the store.  If it is in
        # the store, it also touches the flag file so that the cleanup
        # routine can know the last time an entry was used.
        flag = self._getFlagPath(key)

        if self.context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")

        ret = self._retry(self.context, self.context.client.exists,
                          flag)
        if not ret:
            return False
        self._retry(self.context, self.context.client.set,
                    flag, b'')
        return True

    @staticmethod
    def _retryableSave(context, path, flag, data):
        with sharding.BufferedShardWriter(context.client, path) as stream:
            stream.truncate(0)
            stream.write(data)
            stream.flush()
            context.client.ensure_path(flag)
            compressed_size = stream.compressed_bytes_written
            context.cumulative_write_time += stream.cumulative_write_time
            context.cumulative_write_objects += 1
            context.cumulative_write_znodes += stream.znodes_written
            context.cumulative_write_bytes += compressed_size
        return compressed_size

    def put(self, data):
        if isinstance(self.context, LocalZKContext):
            return None

        if self.context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")

        hasher = hashlib.sha256()
        hasher.update(data)
        key = hasher.hexdigest()

        path = self._getPath(key)
        flag = self._getFlagPath(key)

        if self._checkKey(key):
            return key

        with locked(
                SessionAwareLock(
                    self.context.client,
                    f"{self.lock_root}/{key}"),
                blocking=True
        ) as lock:
            if self._checkKey(key):
                return key

            # make a new context based on the old one
            locked_context = ZKContext(self.context.client, lock,
                                       self.context.stop_event,
                                       self.context.log)

            self._retry(
                locked_context,
                self._retryableSave,
                locked_context, path, flag, data)
            self.context.updateStatsFromOtherContext(locked_context)
        return key

    def delete(self, key, ltime):
        path = self._getRootPath(key)
        flag = self._getFlagPath(key)
        if self.context.sessionIsInvalid():
            raise Exception("ZooKeeper session or lock not valid")
        try:
            with locked(
                    SessionAwareLock(
                        self.context.client,
                        f"{self.lock_root}/{key}"),
                    blocking=True
            ) as lock:
                # make a new context based on the old one
                locked_context = ZKContext(self.context.client, lock,
                                           self.context.stop_event,
                                           self.context.log)

                # Double check that it hasn't been used since we
                # decided to delete it
                data, zstat = self._retry(locked_context,
                                          self.context.client.get,
                                          flag)
                if zstat.last_modified_transaction_id < ltime:
                    self._retry(locked_context, self.context.client.delete,
                                path, recursive=True)
        except NoNodeError:
            raise KeyError(key)

    def __iter__(self):
        try:
            hashdirs = self.context.client.get_children(self.data_root)
        except NoNodeError:
            return

        for hashdir in hashdirs:
            try:
                for key in self.context.client.get_children(
                        f'{self.data_root}/{hashdir}'):
                    yield key
            except NoNodeError:
                pass

    def __len__(self):
        return len([x for x in self])

    def getKeysLastUsedBefore(self, ltime):
        ret = set()
        for key in self:
            flag = self._getFlagPath(key)
            data, zstat = self._retry(self.context, self.context.client.get,
                                      flag)
            if zstat.last_modified_transaction_id < ltime:
                ret.add(key)
        return ret
