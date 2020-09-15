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
import time
from typing import Optional, Dict, Any, Callable, Tuple, Union, List
import re

from kazoo.client import KazooClient
from kazoo.exceptions import LockTimeout
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.zk import ZooKeeperClient
from zuul.zk.base import ZooKeeperBase
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperTreeCacheClient, L


class ZooKeeperBuildTreeCacheClient(
        ZooKeeperTreeCacheClient[ZooKeeperBuildItem]):

    def __init__(self, client: KazooClient, zone: Optional[str] = None,
                 multilevel: bool = False,
                 listener: Optional[L] = None):
        root = "%s/%s" % (ZooKeeperBuilds.ROOT, zone)\
            if zone else ZooKeeperBuilds.ROOT
        super().__init__(client, root, multilevel, listener)

    def _create_cached_value(self, path: str, content: Dict[str, Any],
                             stat: ZnodeStat) -> ZooKeeperBuildItem:
        return ZooKeeperBuildItem(path, content, stat)


class ZooKeeperBuilds(ZooKeeperBase):
    """
    Build relevant methods for ZooKeeper
    """
    ROOT = "/zuul/builds"
    DEFAULT_ZONE = "default-zone"

    log = logging.getLogger("zuul.zk.builds.ZooKeeperBuilds")

    def __init__(self, client: ZooKeeperClient, enable_cache: bool):
        super().__init__(client)

        self.__enable_cache = enable_cache  # type: bool
        self.__builds_cache_started = False  # type: bool
        self.__builds_cache =\
            {}  # type: Dict[str, ZooKeeperBuildTreeCacheClient]
        self.__builds_cache_listeners = []  # type: List[L]
        self.__build_locks = {}  # type: Dict[str, Lock]
        self.hold_in_queue = False  # type: bool

    def _on_connect(self):
        if self.__enable_cache:
            self.__builds_cache_started = True
            for builds_cache in self.__builds_cache.values():
                builds_cache.start()

    def _on_disconnect(self):
        self.__builds_cache_started = False
        for builds_cache in self.__builds_cache.values():
            builds_cache.stop()

    def __cached_item(self, path: str):
        for builds_cache in self.__builds_cache.values():
            cached = builds_cache[path]
            if cached:
                return cached
        return None

    def register_cache_listener(self, listener):
        if listener not in self.__builds_cache_listeners:
            self.__builds_cache_listeners.append(listener)
        for cache in self.__builds_cache.values():
            cache.register_listener(listener)

    def register_zone(self, zone: Optional[str] = None):
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        zone = zone or self.DEFAULT_ZONE
        if self.__enable_cache \
                and zone not in self.__builds_cache:
            builds_cache = ZooKeeperBuildTreeCacheClient(self.kazoo_client,
                                                         zone)
            if self.__builds_cache_started:
                builds_cache.start()
            for listener in self.__builds_cache_listeners:
                builds_cache.register_listener(listener)
            self.__builds_cache[zone] = builds_cache

    def register_all_zones(self):
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        for zone in self.kazoo_client.get_children(self.ROOT):
            self.register_zone(zone)

    def set_hold_in_queue(self, hold: bool):
        self.hold_in_queue = hold

    def release(self, what: Union[None, str, ZooKeeperBuildItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        if isinstance(what, ZooKeeperBuildItem):
            what.content['state'] = 'REQUESTED'
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding='UTF-8'),
                version=what.stat.version)
        else:
            for path, cached in self.__in_state(lambda s: s == 'HOLD'):
                if not what or re.match(what, cached.content['params']['job']):
                    cached.content['state'] = 'REQUESTED'
                    self.kazoo_client.set(
                        path,
                        json.dumps(cached.content).encode(encoding='UTF-8'),
                        version=cached.stat.version)

    def wait_until_released(self,
                            what: Union[None, str, ZooKeeperBuildItem] = None):
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        paths = []  # type: List[str]
        if isinstance(what, ZooKeeperBuildItem):
            paths = [what.path]
        else:
            for builds_cache in list(self.__builds_cache.values()):
                for path, cached in list(builds_cache.items()):
                    job_name = cached.content['params']['job']
                    if not what or re.match(what, job_name):
                        paths.append(path)

        self.log.debug("Waiting for %s to be released" % paths)

        while True:
            on_hold = []
            for builds_cache in list(self.__builds_cache.values()):
                for path, cached in list(builds_cache.items()):
                    if path in paths and cached.content['state'] == 'HOLD':
                        on_hold.append(path)
            if len(on_hold) == 0:
                self.log.debug("%s released" % what)
                return
            else:
                self.log.debug("Still waiting for %s to be released" % on_hold)

    def submit(self, uuid: str, params: Dict[str, Any], zone: Optional[str],
               precedence: int) -> str:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.register_zone(zone)

        self.kazoo_client.ensure_path(self.ROOT)

        path = '{}/{}/{:0>3}-'.format(self.ROOT,
                                      zone or self.DEFAULT_ZONE,
                                      precedence)
        content = json_dumps(dict(
            uuid=uuid,
            zone=zone or self.DEFAULT_ZONE,
            precedence=precedence,
            # REQUESTED, HOLD, RUNNING, PAUSED, COMPLETED, FAILED
            state='HOLD' if self.hold_in_queue else 'REQUESTED',
            params=params,
        )).encode(encoding='UTF-8')
        node = self.kazoo_client.create(path, content, sequence=True,
                                        makepath=True)
        self.log.debug("Build %s submitted" % node)
        return node

    def __in_state(self, condition: Callable[[str], bool])\
            -> List[Tuple[str, ZooKeeperBuildItem]]:
        """
        Gets builds satisfying state 'condition'.

        :param condition: A condition build's state must satisfy.
        :return: List of builds (tuple path and object) satisfying given state
                 condition.
        """
        # TODO JK: Make sure this is sorted by key (x[0])
        builds = []
        for builds_cache in list(self.__builds_cache.values()):
            for path, cached in list(builds_cache.items()):
                if condition(cached.content['state']):
                    builds.append((path, cached))
        return builds

    def in_state(self, state: Union[str, List[str]])\
            -> List[Tuple[str, ZooKeeperBuildItem]]:
        states = [state] if isinstance(state, str) else state
        return self.__in_state(lambda s: s in states)

    @property
    def all(self) -> List[Tuple[str, ZooKeeperBuildItem]]:
        return self.__in_state(lambda s: True)

    def get(self, path: str) -> Optional[ZooKeeperBuildItem]:
        for cache in self.__builds_cache.values():
            cached = cache[path]
            if cached:
                return cached
        return None

    def wait_until_cache_state(self,
                               condition: Callable[
                                   [Dict[str, ZooKeeperBuildTreeCacheClient]],
                                   bool]):
        while not condition(self.__builds_cache):
            self.log.debug("Cache state does not match!")
            time.sleep(0.1)
        self.log.debug("Cache state does match")

    def get_lock(self, path: str) -> Lock:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        return self.__build_locks.get(path, self.kazoo_client.Lock(path))

    def next(self) -> Optional[ZooKeeperBuildItem]:
        """
        Retrieves next build in state `REQUESTED` and cleans builds started on
        executors which died.

        :return: ZooKeeperBuildItem or None if no next build item is available
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        # TODO JK: __in_state should return a sorted dict
        builds = sorted(self.__in_state(
            lambda s: s not in ['HOLD', 'COMPLETED', 'FAILED', 'CANCELED']),
            key=lambda x: x[0])
        for path, cached in builds:
            self.log.debug("Next build candidate: %s [%s]" % (
                path, cached.content['state']))

            # First filter to significantly lower node count
            if cached.content['state'] not in ['HOLD', 'COMPLETED', 'FAILED',
                                               'CANCELED']:
                lock = self.get_lock(path)
                if cached.content['state'] == 'REQUESTED':
                    try:
                        lock.acquire(timeout=10.0)
                        cached.content['state'] = 'RUNNING'
                        self.kazoo_client.set(path, json.dumps(cached.content)
                                              .encode(encoding='UTF-8'))
                        if isinstance(cached, ZooKeeperBuildItem):
                            self.__build_locks[path] = lock
                            self.log.debug("Next build: %s" % path)
                            return cached
                        else:
                            lock.release()
                            raise Exception("%s is not a build item" % cached)
                    except LockTimeout:
                        self.log.warning(
                            "Next [%s] Lock could not be acquired!" %
                            path)
                elif cached.content['state'] == 'HOLD':
                    continue
                # not in ['HOLD', 'REQUESTED', 'COMPLETED', 'FAILED',
                #         'CANCELED']:
                elif not lock.is_acquired\
                        and cached.content['state'] != 'COMPLETED':
                    try:
                        # If one can acquire a lock then the executor
                        # which started that build died -> update state
                        # accordingly
                        lock.acquire(timeout=1.0)
                        if cached.content['state'] != 'COMPLETED':
                            cached.content['state'] = 'FAILED'
                            self.kazoo_client.set(
                                path, json.dumps(cached.content).encode(
                                    encoding='UTF-8'))
                            self.log.warning("Next [%s] %s: FAILED" % (
                                             path, json.dumps(cached.content)))
                    except LockTimeout:
                        pass
                    finally:
                        lock.release()
        return None

    def is_locked(self, path: str) -> bool:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks.get(path)
        return lock is not None and lock.is_acquired

    def pause(self, path: str) -> bool:
        """
        Pauses a build.

        :param path: Path representing the build's node
        :return: True if pausing succeeded
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.log.debug("pause: %s" % path)
        lock = self.__build_locks[path]
        if lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % path
            if self.kazoo_client.exists(resume_node):
                self.kazoo_client.delete(resume_node)

            cached = self.__cached_item(path)
            if cached and cached.content['state'] == 'RUNNING':
                cached.content['state'] = 'PAUSED'
                self.kazoo_client.set(path, json.dumps(cached.content)
                                      .encode(encoding='UTF-8'),
                                      version=cached.stat.version)
                self.log.debug("pause: Pausing %s" % path)
                return True
            elif not cached:
                raise Exception("Build node %s is not cached!" % path)

        self.log.debug("pause: Not pausing %s" % path)
        return False

    def resume_request(self, path: str) -> None:
        """
        Requests resuming a build
        :param path: Path representing the build's node
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.log.debug("resume_request: %s" % path)
        self.kazoo_client.ensure_path("%s/resume" % path)

    def resume_attempt(self, path: str,
                       action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to resume a build which is in `PAUSED` state and where resume
        was requested using `#resume_request`.

        :param path: Path representing the build's node
        :param action: Action to call to actually resume the build
        :return: True if resume attempt was successful
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        # self.log.debug("resume_attempt: %s" % path)
        lock = self.__build_locks[path]
        cached = self.__cached_item(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] == 'PAUSED'\
                and cached.resume:
            cached.content['state'] = 'RUNNING'
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            action(cached)
            self.kazoo_client.delete("%s/resume" % path)
            return True
        elif not cached:
            raise Exception("Build node is not cached!")

        return False

    def complete(self, path: str, success: bool = True) -> bool:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.log.debug("Complete: %s" % path)
        lock = self.__build_locks[path]
        # cached = self.__cached_item(path)
        data, stat = self.kazoo_client.get(path)
        content = json.loads(data.decode('UTF-8'))
        if content and lock.is_acquired\
                and content['state'] == 'RUNNING':
            content['state'] = 'COMPLETED' if success else 'FAILED'
            self.kazoo_client.set(path, json.dumps(content)
                                  .encode(encoding='UTF-8'),
                                  version=stat.version)
            lock.release()
            return True
        return False

    def cancel_in_queue(self, path: str) -> None:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.log.debug("cancel_in_queue: %s" % path)
        cached = self.__cached_item(path)
        if cached and cached.content['state'] in ['HOLD', 'REQUESTED']:
            cached.content['state'] = 'CANCELED'
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'))

    def cancel_request(self, path: str) -> None:
        """
        Requests canceling a build
        :param path: Path representing a build node
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.log.debug("Cancel request: %s/cancel" % path)
        self.kazoo_client.ensure_path("%s/cancel" % path)

    def cancel_attempt(self, path: str,
                       action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to cancel a build where cancellation was requested using
        `#cancel_request`.

        :param path: Path representing the build's node
        :param action: Action to call to actually cancel the build
        :return: True if cancel attempt was successful
        """
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        cached = self.__cached_item(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] in ['RUNNING', 'PAUSED']\
                and cached.cancel:

            self.log.debug("Cancel attempt: Canceled %s" % path)
            cached.content['state'] = 'CANCELED'
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            action(cached)
            self.kazoo_client.delete("%s/cancel" % path)
            return True

        return False

    def status(self, path: str, progress: int, total: int) -> None:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        self.data(path, dict(progress=progress, total=total), key='status')

    def data(self, path: str, data: Dict[str, Any], key: str = 'data')\
            -> None:
        if not self.kazoo_client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        if lock.is_acquired:
            node = "%s/%s" % (path, key)
            value = json.dumps(data).encode(encoding='UTF-8')
            stat = self.kazoo_client.exists(node)
            if stat:
                self.kazoo_client.set(node, value, version=stat.version)
            else:
                self.kazoo_client.create(node, value)
        else:
            raise Exception("Lock not acquired!")
