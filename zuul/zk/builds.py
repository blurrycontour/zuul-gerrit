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
from typing import Optional, Dict, Any, Callable, Tuple, TYPE_CHECKING,\
    Iterator

from kazoo.exceptions import LockTimeout
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock

from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperBuildTreeCacheClient


class ZooKeeperBuildsMixin(object):
    """
    Build relevant methods for ZooKeeper
    """
    ZUUL_BUILDS_ROOT = "/zuul/builds"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        self.__builds_cache = ZooKeeperBuildTreeCacheClient(
            self, self.ZUUL_BUILDS_ROOT)  # type: ZooKeeperBuildTreeCacheClient
        self.__build_locks = {}  # type: Dict[str, Lock]

    def _startCaching(self) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if self.enable_cache:
            self.__builds_cache.start()

    def _stopCaching(self) -> None:
        self.__builds_cache.stop()

    def submitBuild(self, uuid: str, params: Dict[str, Any], precedence: int,
                    watcher: Callable[[str, Dict[str, Any]], None]) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        self.client.ensure_path(self.ZUUL_BUILDS_ROOT)

        path = '{}/{:0>3}-'.format(self.ZUUL_BUILDS_ROOT, precedence)
        content = json.dumps(dict(
            uuid=uuid,
            precedence=precedence,
            state='REQUESTED'  # REQUESTED, RUNNING, PAUSED, COMPLETED, FAILED
        )).encode(encoding='UTF-8')
        node = self.client.create(path, content, sequence=True, makepath=True)

        try:
            params_data = json.dumps(params).encode(encoding='UTF-8')
            self.client.create("%s/params" % node, params_data)

            # TODO JK: Not needed, use TreeCache (__builds_cache)
            class Watcher:
                def __init__(self, unique: str,
                             cb: Callable[[str, Dict[str, Any]], None]):
                    self.unique = unique
                    self.cb = cb

                def __call__(self, content, stat: ZnodeStat, event):
                    data = json.loads(content.decode('UTF-8'))\
                        if content else None
                    self.cb(self.unique, data)

            self.client.DataWatch(node, Watcher(uuid, watcher))
        except Exception as e:
            # TODO JK: For breakpoint - should not be happening -> analyze json
            # object
            self.log.error("Exception: %s" % e)
        return node

    def __getBuildsInState(self, condition: Callable[[str], bool])\
            -> Iterator[Tuple[str, Any]]:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        # TODO JK: Make sure this is sorted by key (x[0])
        return map(lambda x: (x[0], x[1]),
                   filter(lambda x: condition(x[1].content['state']),
                          self.__builds_cache.items()))

    def getNextBuild(self) -> Optional[ZooKeeperBuildItem]:
        """
        Retrieves next job in state `REQUESTED` and cleans jobs stated on
        executors which died.

        :return: Lock, Job tuple
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        # TODO JK: __getBuildsInState should return a sorted dict
        for key, cached in sorted(self.__getBuildsInState(
                lambda s: s not in ['COMPLETED', 'FAILED']),
                key=lambda x: x[0]):
            path = "%s/%s" % (self.ZUUL_BUILDS_ROOT, key)

            # First filter to significantly lower node count
            if cached.content['state'] not in ['COMPLETED', 'FAILED']:
                lock = self.client.Lock(path)
                if cached.content['state'] == 'REQUESTED':
                    try:
                        lock.acquire(timeout=10.0)
                        cached.content['state'] = 'RUNNING'
                        self.client.set(path, json.dumps(cached.content)
                                        .encode(encoding='UTF-8'))
                        if isinstance(cached, ZooKeeperBuildItem):
                            self.log.debug("getNextJob [%s] %s: %s" % (
                                           lock.path,
                                           json.dumps(cached.content),
                                           json.dumps(cached.params)))
                            self.__build_locks[path] = lock
                            return cached
                        else:
                            lock.release()
                            raise Exception("%s is not a build item" % cached)
                    except LockTimeout:
                        self.log.warning(
                            "getNextJob [%s] Lock could not be acquired!" %
                            lock.path)
                else:  # not in ['REQUESTED', 'COMPLETED', 'FAILED']:
                    try:
                        # If one can acquire a lock then the executor
                        # which started that job died -> update state
                        # accordingly
                        lock.acquire(timeout=1.0)
                        cached.content['state'] = 'FAILED'
                        self.client.set(path, json.dumps(cached.content)
                                        .encode(encoding='UTF-8'))
                        self.log.warning("getNextJob [%s] %s: FAILED" % (
                                         lock.path,
                                         json.dumps(cached.content)))
                    except LockTimeout:
                        pass
                    finally:
                        lock.release()
        return None

    def isBuildLocked(self, path) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        return lock and lock.is_acquired

    def pauseBuild(self, path: str) -> bool:
        """
        Pauses a build.

        :param lock: Lock representing the build's node
        :return: True if pausing succeeded
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        if lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % lock.path
            if self.client.exists(resume_node):
                self.client.delete(resume_node)

            key = lock.path.rsplit('/', 1)[1]
            cached = self.__builds_cache[key]
            if cached and cached.content['state'] == 'RUNNING':
                cached.content['state'] = 'PAUSED'
                self.client.set(lock.path, json.dumps(cached.content)
                                .encode(encoding='UTF-8'))
                self.log.debug("pauseBuild: Pausing")
                return True
            elif not cached:
                raise Exception("Build node is not cached!")

        self.log.debug("pauseBuild: Not pausing")
        return False

    def resumeBuildRequest(self, node: str) -> None:
        """
        Requests resuming a build
        :param node: Node representing a build
        """
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        self.log.debug("resumeBuildRequest")
        self.client.ensure_path("%s/resume" % node)

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

        lock = self.__build_locks[path]
        key = lock.path.rsplit('/', 1)[1]
        cached = self.__builds_cache[key]
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] == 'PAUSED'\
                and cached.resume:
            cached.content['state'] = 'RUNNING'
            self.client.set(lock.path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'))
            action(cached)
            self.client.delete("%s/resume" % lock.path)
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

        lock = self.__build_locks[path]
        key = lock.path.rsplit('/', 1)[1]
        cached = self.__builds_cache[key]
        if cached and lock.is_acquired and\
                cached.content['state'] == 'RUNNING':
            cached.content['state'] = 'COMPLETED' if success else 'FAILED'
            self.client.set(lock.path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'))
            lock.release()
            return True
        return False

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

        self.log.debug("cancelBuildRequest")
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

        lock = self.__build_locks[path]
        sequence = lock.path.rsplit('/', 1)[1]
        cached = self.__builds_cache[sequence]
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock.is_acquired\
                and cached.content['state'] in ['RUNNING', 'PAUSED']\
                and cached.cancel:
            cached.content['state'] = 'COMPLETED'  # TODO JK: CANCELED?
            self.client.set(lock.path, json.dumps(cached.content)
                            .encode(encoding='UTF-8'))
            action(cached)
            self.client.delete("%s/cancel" % lock.path)
            return True

        return False

    def setBuildStatus(self, path: str, progress: int, total: int) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        self.setBuildData(path, 'status', dict(progress=progress, total=total))

    def setBuildData(self, path: str, key: str, data: Dict[str, Any]) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        lock = self.__build_locks[path]
        if lock.is_acquired:
            node = "%s/%s" % (lock.path, key)
            value = json.dumps(data).encode(encoding='UTF-8')
            if self.client.exists(node):
                self.client.set(node, value)
            else:
                self.client.create(node, value)
        else:
            raise Exception("Lock not acquired!")
