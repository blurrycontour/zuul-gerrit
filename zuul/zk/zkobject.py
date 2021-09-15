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

import json
import time

from kazoo.exceptions import ZookeeperError


class ZKContext:
    def __init__(self, zk_client, lock, stop_event, log):
        self.client = zk_client.client
        self.lock = lock
        self.stop_event = stop_event
        self.log = log

    def sessionIsValid(self):
        return (not self.lock or self.lock.is_still_valid() and
                not self.stop_event or not self.stop_event.is_set())


class ZKObject:
    ### Implementations of these two methods are required
    def getPath(self):
        """Return the path to save this object in ZK

        :returns: A string representation of the Znode path
        """
        raise NotImplementedError()

    def serialize(self):
        """Implement this method to return the data to save in ZK.

        :returns: A byte string
        """
        raise NotImplementedError()

    ### This should work for most classes
    def deserialize(self, data):
        """Implement this method to return the data to save in ZK.

        :param bytes data: A byte string to deserialize

        :returns: A dictionary of attributes and values to be set on
        the object.
        """
        return json.loads(data.decode('utf-8'))

    ### These methods are public and shouldn't need to be overridden
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
        old = self.__dict__
        self._set(**kw)
        try:
            self._save(context)
        except Exception:
            # Roll back our old values if we aren't able to update ZK.
            self._set(**old)
            raise

    @classmethod
    def new(klass, context, **kw):
        """Create a new instance and save it in ZooKeeper"""
        obj = klass()
        obj._set(**kw)
        obj._save(context, create=True)
        return obj

    @classmethod
    def fromZK(klass, context, path):
        """Instantiate a new object from data in ZK"""
        obj = klass()
        obj._load(context, path=path)
        return obj

    def refresh(self, context):
        """Update data from ZK"""
        self._load(context)

    def delete(self, context):
        path = self.getPath()
        while context.sessionIsValid():
            try:
                context.client.delete(path)
                return
            except ZookeeperError:
                # These errors come from the server and are not
                # retryable.  Connection errors are KazooExceptions so
                # they aren't caught here and we will retry.
                raise
            except Exception:
                context.log.exception(
                    "Exception deleting ZKObject %s, will retry", self)
                time.sleep(5)
        raise Exception("ZooKeeper session or lock not valid")

    ### Private methods below

    def __init__(self):
        # Don't support any arguments in constructor to force us to go
        # through a save or restore path.
        super().__init__()

    def _load(self, context, path=None):
        if path is None:
            path = self.getPath()
        while context.sessionIsValid():
            try:
                data, zstat = context.client.get(path)
                self._set(**self.deserialize(data))
                self._set(_zstat=zstat)
                return
            except ZookeeperError:
                # These errors come from the server and are not
                # retryable.  Connection errors are KazooExceptions so
                # they aren't caught here and we will retry.
                raise
            except Exception:
                context.log.exception(
                    "Exception loading ZKObject %s, will retry", self)
                time.sleep(5)
        raise Exception("ZooKeeper session or lock not valid")

    def _save(self, context, create=False):
        data = self.serialize()
        path = self.getPath()
        while context.sessionIsValid():
            try:
                if create:
                    real_path, zstat = context.client.create(
                        path, data, include_data=True)
                else:
                    zstat = context.client.set(path, data,
                                               version=self._zstat.version)
                self._set(_zstat=zstat)
                return
            except ZookeeperError:
                # These errors come from the server and are not
                # retryable.  Connection errors are KazooExceptions so
                # they aren't caught here and we will retry.
                raise
            except Exception:
                context.log.exception(
                    "Exception saving ZKObject %s, will retry", self)
                time.sleep(5)
        raise Exception("ZooKeeper session or lock not valid")

    def __setattr__(name, value):
        raise Exception("Unable to modify ZKObject %s" %
                        (repr(self),))

    def _set(self, **kw):
        for name, value in kw.items():
            super().__setattr__(name, value)
