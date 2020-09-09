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
from typing import Optional, Dict, Any, Callable, Tuple, TYPE_CHECKING, \
    Union, List
import re

from kazoo.exceptions import LockTimeout
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperBuildTreeCacheClient


class ZooKeeperBuildsMixin(object):
    """
    Build relevant methods for ZooKeeper
    """
    ZUUL_BUILDS_ROOT = "/zuul/builds"
    ZUUL_BUILDS_DEFAULT_ZONE = "default-zone"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        # TODO: DICT ZONE -> TreeCache
        self.__builds_cache_started = False
        self.__builds_cache =\
            {}  # type: Dict[str, ZooKeeperBuildTreeCacheClient]
        self.__builds_cache_listeners = []
        self.__build_locks = {}  # type: Dict[str, Lock]
        self.builds_hold_in_queue = False  # type: bool

    def _startCaching(self) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if self.enable_cache:
            self.__builds_cache_started = True
            for builds_cache in self.__builds_cache.values():
                builds_cache.start()

    def _stopCaching(self) -> None:
        self.__builds_cache_started = False
        for builds_cache in self.__builds_cache.values():
            builds_cache.start()

    def __getCachedItem(self, path: str):
        for builds_cache in self.__builds_cache.values():
            cached = builds_cache[path]
            if cached:
                return cached
        return None

    def registerBuildTreeCacheListener(self, listener):
        if listener not in self.__builds_cache_listeners:
            self.__builds_cache_listeners.append(listener)
        for cache in self.__builds_cache.values():
            cache.registerListener(listener)

    def registerBuildZone(self, zone: Optional[str]=None):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        zone = zone or self.ZUUL_BUILDS_DEFAULT_ZONE
        if self.enable_cache and zone not in self.__builds_cache:
            builds_cache = ZooKeeperBuildTreeCacheClient(self, zone)
            if self.__builds_cache_started:
                builds_cache.start()
            for listener in self.__builds_cache_listeners:
                builds_cache.registerListener(listener)
            self.__builds_cache[zone] = builds_cache

    def registerAllBuildZones(self):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        for zone in self.client.get_children(self.ZUUL_BUILDS_ROOT):
            self.registerBuildZone(zone)

    def holdBuildsInQueue(self, hold: bool):
        self.builds_hold_in_queue = hold

    def submitBuild(self, uuid: str, params: Dict[str, Any],
                    zone: Optional[str], precedence: int) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.registerBuildZone(zone)

        self.client.ensure_path(self.ZUUL_BUILDS_ROOT)

        path = '{}/{}/{:0>3}-'.format(self.ZUUL_BUILDS_ROOT,
                                      zone or self.ZUUL_BUILDS_DEFAULT_ZONE,
                                      precedence)
        content = json_dumps(dict(
            uuid=uuid,
            zone=zone or self.ZUUL_BUILDS_DEFAULT_ZONE,
            precedence=precedence,
            # REQUESTED, HOLD, RUNNING, PAUSED, COMPLETED, FAILED
            state='HOLD' if self.builds_hold_in_queue else 'REQUESTED',
            params=params,
        )).encode(encoding='UTF-8')
        node = self.client.create(path, content, sequence=True, makepath=True)
        self.log.debug("Build %s submitted" % node)
        return node

    def releaseBuilds(self, what: Union[None, str, ZooKeeperBuildItem]=None):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        if isinstance(what, ZooKeeperBuildItem):
            what.content['state'] = 'REQUESTED'
            self.client.set(what.path, json.dumps(what.content)
                            .encode(encoding='UTF-8'))
        else:
            for path, cached in self.__getBuildsInState(lambda s: s == 'HOLD'):
                if not what or re.match(what, cached.content['params']['job']):
                    cached.content['state'] = 'REQUESTED'
                    self.client.set(path, json.dumps(cached.content)
                                    .encode(encoding='UTF-8'))

    def __getBuildsInState(self, condition: Callable[[str], bool])\
            -> List[Tuple[str, ZooKeeperBuildItem]]:
        """
        Gets builds satisfying state 'condition'.

        :param condition: A condition build's state must satisfy.
        :return: List of builds (tuple path and object) satisfying given state
                 condition.
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        # TODO JK: Make sure this is sorted by key (x[0])
        builds = []
        for builds_cache in list(self.__builds_cache.values()):
            for path, cached in list(builds_cache.items()):
                if condition(cached.content['state']):
                    builds.append((path, cached))
        return builds

    def getBuildsInState(self, state: Union[str, List[str]])\
            -> List[Tuple[str, ZooKeeperBuildItem]]:
        states = [state] if isinstance(state, str) else state
        return self.__getBuildsInState(lambda s: s in states)

    def getAllBuilds(self) -> List[Tuple[str, ZooKeeperBuildItem]]:
        return self.__getBuildsInState(lambda s: True)

    def getBuildItem(self, path: str) -> Optional[ZooKeeperBuildItem]:
        for cache in self.__builds_cache.values():
            cached = cache[path]
            if cached:
                return cached
        return None

    def getNextBuild(self) -> Optional[ZooKeeperBuildItem]:
        """
        Retrieves next build in state `REQUESTED` and cleans builds started on
        executors which died.

        :return: ZooKeeperBuildItem or None if no next build item is available
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        # TODO JK: __getBuildsInState should return a sorted dict
        builds = sorted(self.__getBuildsInState(
            lambda s: s not in ['HOLD', 'COMPLETED', 'FAILED']),
            key=lambda x: x[0])
        for path, cached in builds:
            self.log.debug("Next build candidate: %s [%s]" % (
                path, cached.content['state']))

            # First filter to significantly lower node count
            if cached.content['state'] not in ['HOLD', 'COMPLETED', 'FAILED']:
                lock = self.__build_locks.get(path, self.client.Lock(path))
                if cached.content['state'] == 'REQUESTED':
                    try:
                        lock.acquire(timeout=10.0)
                        cached.content['state'] = 'RUNNING'
                        self.client.set(path, json.dumps(cached.content)
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
                            "getNextBuild [%s] Lock could not be acquired!" %
                            path)
                elif cached.content['state'] == 'HOLD':
                    continue
                # not in ['HOLD', 'REQUESTED', 'COMPLETED', 'FAILED']:
                elif not lock.is_acquired\
                        and cached.content['state'] != 'COMPLETED':
                    try:
                        # If one can acquire a lock then the executor
                        # which started that build died -> update state
                        # accordingly
                        lock.acquire(timeout=1.0)
                        if cached.content['state'] != 'COMPLETED':
                            cached.content['state'] = 'FAILED'
                            self.client.set(path, json.dumps(cached.content)
                                            .encode(encoding='UTF-8'))
                            self.log.warning("getNextBuild [%s] %s: FAILED" % (
                                             path, json.dumps(cached.content)))
                    except LockTimeout:
                        pass
                    finally:
                        lock.release()
        return None

    def isBuildLocked(self, path: str) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks.get(path)
        return lock is not None and lock.is_acquired

    def pauseBuild(self, path: str) -> bool:
        """
        Pauses a build.

        :param path: Path representing the build's node
        :return: True if pausing succeeded
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.log.debug("pauseBuild: %s" % path)
        lock = self.__build_locks[path]
        if lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % path
            if self.client.exists(resume_node):
                self.client.delete(resume_node)

            cached = self.__getCachedItem(path)
            if cached and cached.content['state'] == 'RUNNING':
                cached.content['state'] = 'PAUSED'
                self.client.set(path, json.dumps(cached.content)
                                .encode(encoding='UTF-8'),
                                version=cached.stat.version)
                self.log.debug("pauseBuild: Pausing %s" % path)
                return True
            elif not cached:
                raise Exception("Build node %s is not cached!" % path)

        self.log.debug("pauseBuild: Not pausing %s" % path)
        return False

    def resumeBuildRequest(self, path: str) -> None:
        """
        Requests resuming a build
        :param path: Path representing the build's node
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.log.debug("resumeBuildRequest: %s" % path)
        self.client.ensure_path("%s/resume" % path)

    def resumeBuildAttempt(self, path: str,
                           action: Callable[[ZooKeeperBuildItem], None])\
            -> bool:
        """
        Tries to resume a build which is in `PAUSED` state and where resume
        was requested using `#resumeBuildRequest`.

        :param path: Path representing the build's node
        :param action: Action to call to actually resume the build
        :return: True if resume attempt was successful
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        # self.log.debug("resumeBuildAttempt: %s" % path)
        lock = self.__build_locks[path]
        cached = self.__getCachedItem(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] == 'PAUSED'\
                and cached.resume:
            cached.content['state'] = 'RUNNING'
            self.client.set(path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'),
                            version=cached.stat.version)
            action(cached)
            self.client.delete("%s/resume" % path)
            return True
        elif not cached:
            raise Exception("Build node is not cached!")

        return False

    def completeBuild(self, path: str, success: bool=True) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.log.debug("completeBuild: %s" % path)
        lock = self.__build_locks[path]
        # cached = self.__getCachedItem(path)
        data, stat = self.client.get(path)
        content = json.loads(data.decode('UTF-8'))
        if content and lock.is_acquired\
                and content['state'] == 'RUNNING':
            content['state'] = 'COMPLETED' if success else 'FAILED'
            self.client.set(path, json.dumps(content)
                            .encode(encoding='UTF-8'),
                            version=stat.version)
            lock.release()
            return True
        return False

    def cancelBuildInQueue(self, path: str) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.log.debug("cancelBuildInQueue: %s" % path)
        cached = self.__getCachedItem(path)
        if cached and cached.content['state'] == 'REQUESTED':
            cached.content['state'] = 'COMPLETED'
            self.client.set(path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'))

    def cancelBuildRequest(self, path: str) -> None:
        """
        Requests canceling a build
        :param path: Path representing a build node
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.log.debug("cancelBuildRequest: %s/cancel" % path)
        self.client.ensure_path("%s/cancel" % path)

    def cancelBuildAttempt(self, path: str,
                           action: Callable[[ZooKeeperBuildItem], None])\
            -> bool:
        """
        Tries to cancel a build where cancelation was requested using
        `#cancelBuildRequest`.

        :param path: Path representing the build's node
        :param action: Action to call to actually cancel the build
        :return: True if cancel attempt was successful
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        # self.log.debug("cancelBuildAttempt: %s" % path)
        lock = self.__build_locks[path]
        cached = self.__getCachedItem(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] in ['RUNNING', 'PAUSED']\
                and cached.cancel:

            self.log.debug("cancelBuildAttempt: Canceled %s" % path)
            cached.content['state'] = 'COMPLETED'  # TODO JK: CANCELED?
            self.client.set(path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'),
                            version=cached.stat.version)
            action(cached)
            self.client.delete("%s/cancel" % path)
            return True

        # self.log.debug("cancelBuildAttempt: Not canceled %s" % path)
        return False

    def setBuildStatus(self, path: str, progress: int, total: int) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.setBuildData(path, dict(progress=progress, total=total),
                          key='status')

    def setBuildData(self, path: str, data: Dict[str, Any], key: str='data')\
            -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        if lock.is_acquired:
            node = "%s/%s" % (path, key)
            value = json.dumps(data).encode(encoding='UTF-8')
            stat = self.client.exists(node)
            if stat:
                self.client.set(node, value, version=stat.version)
            else:
                self.client.create(node, value)
        else:
            raise Exception("Lock not acquired!")
