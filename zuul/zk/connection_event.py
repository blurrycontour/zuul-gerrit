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
from contextlib import contextmanager
from typing import Dict, Callable, List, Any, Generator

from kazoo.exceptions import NoNodeError, LockTimeout
from kazoo.recipe.lock import ReadLock, WriteLock

from zuul.zk import ZooKeeperClient
from zuul.zk.base import ZooKeeperBase


class ZooKeeperConnectionEvent(ZooKeeperBase):
    """
    Class implementing Connection Event specific ZooKeeper interface.
    """
    ROOT = "/zuul/events/connection"

    log = logging.getLogger("zuul.zk.zuul.ZooKeeperConnectionEvent")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self.event_watchers: Dict[str, List[Callable[[List[str]], None]]] = {}

    def _readLock(self, connection_name: str) -> ReadLock:
        lock_node = "%s/%s" % (self.ROOT, connection_name)
        return self.kazoo_client.ReadLock(lock_node)

    def _writeLock(self, connection_name: str) -> WriteLock:
        lock_node = "%s/%s" % (self.ROOT, connection_name)
        return self.kazoo_client.WriteLock(lock_node)

    def watch(self, connection_name: str, watch: Callable[[List[str]], None]):
        if connection_name not in self.event_watchers:
            self.event_watchers[connection_name] = [watch]

            path = "%s/%s/nodes" % (self.ROOT, connection_name)
            self.kazoo_client.ensure_path(path)

            def watchChildren(children):
                if len(children) > 0:
                    for watcher in self.event_watchers[connection_name]:
                        watcher(children)

            self.kazoo_client.ChildrenWatch(path, watchChildren)
        else:
            self.event_watchers[connection_name].append(watch)

    def unwatch(self, connection_name: str):
        if connection_name in self.event_watchers:
            del self.event_watchers[connection_name]

    def hasEvents(self, connection_name: str, keep_locked: bool = False)\
            -> bool:
        lock = self._readLock(connection_name)
        try:
            self.client.acquireLock(lock, keep_locked)
            self.log.debug('hasEvents[%s]: Locked', connection_name)
            path = "%s/%s/nodes" % (self.ROOT, connection_name)
            count = len(self.kazoo_client.get_children(path))
            self.log.debug('hasEvents[%s]: %s', connection_name, count)
            return count > 0
        except LockTimeout:
            self.log.exception('hasEvents[%s]: LockTimeout', connection_name)
            return False
        except NoNodeError:
            self.log.debug('hasEvents[%s]: NoNodeError', connection_name)
            return False
        finally:
            lock.release()
            self.log.debug('hasEvents[%s]: released', connection_name)

    @contextmanager
    def pop(self, connection_name: str)\
            -> Generator[List[Dict[str, Any]], None, None]:
        lock = self._writeLock(connection_name)
        with self.client.withLock(lock):
            events: List[Dict[str, Any]] = []
            path = "%s/%s/nodes" % (self.ROOT, connection_name)
            children = self.kazoo_client.get_children(path)

            for child in sorted(children):
                path = "%s/%s/nodes/%s" % (self.ROOT, connection_name, child)
                data = self.kazoo_client.get(path)[0]
                event = json.loads(data.decode(encoding='utf-8'))
                events.append(event)
                self.kazoo_client.delete(path)

            yield events

    def push(self, connection_name: str, event: Any):
        lock = self._writeLock(connection_name)
        with self.client.withLock(lock):
            path = "%s/%s/nodes/" % (self.ROOT, connection_name)
            self.kazoo_client.create(path, json.dumps(event).encode('utf-8'),
                                     sequence=True, makepath=True)
