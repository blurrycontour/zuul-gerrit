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

import json
import logging
from typing import Dict, Callable, List, Any

from kazoo.exceptions import NoNodeError
from kazoo.recipe.lock import ReadLock, WriteLock

from zuul.zk import ZooKeeperClient
from zuul.zk.base import ZooKeeperBase
from zuul.zk.exceptions import NoClientException


class ZooKeeperConnectionEvent(ZooKeeperBase):
    """
    Class implementing Connection Event specific ZooKeeper interface.
    """
    ROOT = "/zuul/events/connection"

    log = logging.getLogger("zuul.zk.zuul.ZooKeeperConnectionEvent")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self.event_watchers = \
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]

    def __read_lock(self, connection_name: str) -> ReadLock:
        if not self.kazoo_client:
            raise NoClientException()
        lock_node = "%s/%s" % (self.ROOT, connection_name)
        return self.kazoo_client.ReadLock(lock_node)

    def write_lock(self, connection_name: str) -> WriteLock:
        if not self.kazoo_client:
            raise NoClientException()
        lock_node = "%s/%s" % (self.ROOT, connection_name)
        return self.kazoo_client.WriteLock(lock_node)

    def watch(self, connection_name: str, watch: Callable[[List[str]], None]):
        if connection_name not in self.event_watchers:
            self.event_watchers[connection_name] = [watch]

            if not self.kazoo_client:
                raise NoClientException()

            path = "%s/%s/nodes" % (self.ROOT, connection_name)
            self.kazoo_client.ensure_path(path)

            def watch_children(children):
                if len(children) > 0:
                    for watcher in self.event_watchers[connection_name]:
                        watcher(children)

            self.kazoo_client.ChildrenWatch(path, watch_children)
        else:
            self.event_watchers[connection_name].append(watch)

    def unwatch(self, connection_name: str):
        if connection_name in self.event_watchers:
            del self.event_watchers[connection_name]

    def has_events(self, connection_name: str, keep_locked: bool = False)\
            -> bool:
        if not self.kazoo_client:
            raise NoClientException()
        lock = self.__read_lock(connection_name)
        self.client.acquire_lock(lock, keep_locked)
        self.log.debug('hasConnectionEvents[%s]: locked' % connection_name)
        path = "%s/%s/nodes" % (self.ROOT, connection_name)
        try:
            count = len(self.kazoo_client.get_children(path))
            self.log.debug('hasConnectionEvents[%s]: %s' %
                           (connection_name, count))
            return count > 0
        except NoNodeError as e:
            self.log.debug('hasConnectionEvents[%s]: NoNodeError: %s' %
                           (connection_name, e))
            return False
        finally:
            lock.release()
            self.log.debug('hasConnectionEvents[%s]: released' %
                           connection_name)

    def pop(self, connection_name: str):
        if not self.kazoo_client:
            raise NoClientException()

        class EventWrapper:
            def __init__(self, connection_event: 'ZooKeeperConnectionEvent',
                         conn_name: str):
                self.__connection_event = connection_event
                self.__connection_name = conn_name
                self.__lock = self.__connection_event.write_lock(conn_name)

            def __enter__(self):
                self.__connection_event.client.acquire_lock(self.__lock)
                events = []
                path = "%s/%s/nodes" % (self.__connection_event.ROOT,
                                        self.__connection_name)
                children = self.__connection_event.kazoo_client\
                    .get_children(path)

                for child in sorted(children):
                    path = "%s/%s/nodes/%s" % (self.__connection_event.ROOT,
                                               self.__connection_name, child)
                    data = self.__connection_event.kazoo_client.get(path)[0]
                    event = json.loads(data.decode(encoding='utf-8'))
                    events.append(event)
                    self.__connection_event.kazoo_client.delete(path)
                return events

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.__lock.release()

        return EventWrapper(self, connection_name)

    def push(self, connection_name: str, event: Any):
        if not self.kazoo_client:
            raise NoClientException()
        lock = self.write_lock(connection_name)
        self.client.acquire_lock(lock)
        self.log.debug('push: locked')
        try:
            path = "%s/%s/nodes/" % (self.ROOT, connection_name)
            self.kazoo_client.create(path, json.dumps(event).encode('utf-8'),
                                     sequence=True, makepath=True)
        finally:
            lock.release()
            self.log.debug('push: released')
