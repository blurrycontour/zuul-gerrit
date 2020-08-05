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
from typing import Dict, Optional, Callable, List, Any

from kazoo.exceptions import NoNodeError
from kazoo.recipe.lock import ReadLock, WriteLock

from zuul.zk.zuul import ZooKeeperZuulMixin


class ZooKeeperConnectionEventMixin(ZooKeeperZuulMixin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_watchers = \
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]

    def getZuulEventConnectionPath(self, connection_name: str,
                                   path: str, sequence: Optional[str]=None):
        return self._getZuulNodePath('events', 'connection',
                                     connection_name, path, sequence or '')

    def _getConnectionEventReadLock(self, connection_name: str) -> ReadLock:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock_node = self.getZuulEventConnectionPath(connection_name, '')
        return self.client.ReadLock(lock_node)

    def getConnectionEventWriteLock(self, connection_name: str) -> WriteLock:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock_node = self.getZuulEventConnectionPath(connection_name, '')
        return self.client.WriteLock(lock_node)

    def watchConnectionEvents(self, connection_name: str,
                              watch: Callable[[List[str]], None]):
        if connection_name not in self.event_watchers:
            self.event_watchers[connection_name] = [watch]

            if not self.client:
                raise Exception("No zookeeper client!")

            path = self.getZuulEventConnectionPath(connection_name, 'nodes')
            self.client.ensure_path(path)

            def watch_children(children):
                if len(children) > 0:
                    for watcher in self.event_watchers[connection_name]:
                        watcher(children)

            self.client.ChildrenWatch(path, watch_children)
        else:
            self.event_watchers[connection_name].append(watch)

    def unwatchConnectionEvents(self, connection_name: str):
        if connection_name in self.event_watchers:
            del self.event_watchers[connection_name]

    def hasConnectionEvents(self, connection_name: str,
                            keep_locked: bool=False) -> bool:
        if not self.client:
            raise Exception("No zookeeper client!")
        lock = self._getConnectionEventReadLock(connection_name)
        self.acquireLock(lock, keep_locked)
        self.log.debug('hasConnectionEvents[%s]: locked' % connection_name)
        path = self.getZuulEventConnectionPath(connection_name, 'nodes')
        try:
            count = len(self.client.get_children(path))
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

    def popConnectionEvents(self, connection_name: str):
        if not self.client:
            raise Exception("No zookeeper client!")

        class EventWrapper:
            def __init__(self, zk, conn_name: str):
                self.__zk = zk
                self.__connection_name = conn_name
                self.__lock = self.__zk.getConnectionEventWriteLock(conn_name)

            def __enter__(self):
                self.__zk.acquireLock(self.__lock)
                self.__zk.log.debug('popConnectionEvents: locked')
                events = []
                path = self.__zk.getZuulEventConnectionPath(
                    self.__connection_name, 'nodes')
                children = self.__zk.client.get_children(path)

                for child in sorted(children):
                    path = self.__zk.getZuulEventConnectionPath(
                        self.__connection_name, 'nodes', child)
                    data = self.__zk.client.get(path)[0]
                    event = json.loads(data.decode(encoding='utf-8'))
                    events.append(event)
                    self.__zk.client.delete(path)
                return events

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.__lock.release()
                self.__zk.log.debug('popConnectionEvents: released')

        return EventWrapper(self, connection_name)

    def pushConnectionEvent(self, connection_name: str, event: Any):
        if not self.client:
            raise Exception("No zookeeper client!")
        lock = self.getConnectionEventWriteLock(connection_name)
        self.acquireLock(lock)
        self.log.debug('pushConnectionEvent: locked')
        try:
            path = self.getZuulEventConnectionPath(
                connection_name, 'nodes') + '/'
            self.client.create(path, json.dumps(event).encode('utf-8'),
                               sequence=True, makepath=True)
        finally:
            lock.release()
            self.log.debug('pushConnectionEvent: released')
