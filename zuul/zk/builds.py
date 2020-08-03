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
from typing import Optional, Dict, Any, Callable, Tuple, TYPE_CHECKING

from kazoo.exceptions import LockTimeout
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock


class ZooKeeperBuildsMixin:

    def _getBuildPath(self, sequence: Optional[str] = None,
                      path: Optional[str]=None):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        return self._getZuulNodePath('builds', sequence or '', path or '')

    def _getBuildLock(self, sequence: str) -> Lock:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        lock_node = self._getBuildPath(sequence)
        return self.client.Lock(lock_node)

    def submitJob(self, uuid: str, job: Dict[str, Any], precedence: int,
                  watcher: Callable[[str, Dict[str, Any]], None]) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        root = self._getBuildPath()
        self.client.ensure_path(root)

        node = self.client.create(root, b'', sequence=True, makepath=True)
        # self.client.create("%s/uuid" % node, uuid.encode(encoding='UTF-8'))
        # self.client.create("%s/precedence" % node, bytes([precedence]))

        node_data = json.dumps(dict(
            uuid=uuid,
            precedence=precedence,
            state='REQUESTED',
            progress=0,
            max=0))\
            .encode(encoding='UTF-8')
        self.client.create("%s/data" % node, node_data)

        try:
            job_data = json.dumps(job).encode(encoding='UTF-8')
            self.client.create("%s/job" % node, job_data)

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

    def getNextJob(self) -> Optional[Tuple[Lock, Dict[str, Any]]]:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        root = self._getBuildPath()
        self.client.ensure_path(root)
        children = self.client.get_children(root)
        # TODO JK: Children count may grow over time to unacceptable number
        for child in sorted(children):
            node = "%s/%s" % (root, child)
            data_node = "%s/data" % node

            (data_value, _) = self.client.get(data_node)
            data = json.loads(data_value.decode(encoding='UTF-8'))

            # First filter to significantly lower node count
            if data['state'] not in ['COMPLETED', 'FAILED']:
                lock = self.client.Lock(child)
                if data['state'] == 'REQUESTED':
                    try:
                        lock.acquire(timeout=10.0)
                        job_node = "%s/job" % node
                        (job_value, _) = self.client.get(job_node)
                        job = json.loads(job_value.decode(encoding='UTF-8'))

                        data['state'] = 'RUNNING'
                        self.client.set(data_node, json.dumps(data)
                                        .encode(encoding='UTF-8'))
                        self.log.warning(
                            "getNextJob [%s] %s: %s" %
                            lock.path, json.dumps(data), json.dumps(job))
                        return lock, job
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
                        data['state'] = 'FAILED'
                        self.client.set(data_node, json.dumps(data)
                                        .encode(encoding='UTF-8'))
                        self.log.warning("getNextJob [%s] %s: FAILED" %
                                         lock.path, json.dumps(data))
                    except LockTimeout:
                        pass
                    finally:
                        lock.release()
        return None

    def pauseBuild(self, lock: Lock) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        if lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % lock.path
            if self.client.exists(resume_node):
                self.client.delete(resume_node)

            data_node = "%s/data" % lock.path
            (data_value, _) = self.client.get(data_node)
            data = json.loads(data_value.decode(encoding='UTF-8'))

            if data['state'] == 'RUNNING':
                data['state'] = 'PAUSED'
                self.client.set(data_node, json.dumps(data)
                                .encode(encoding='UTF-8'))
                self.log.debug("pauseBuild: Pausing")
                return True
        self.log.debug("pauseBuild: Not pausing")
        return False

    def resumeBuild(self, lock: Lock):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        if lock.is_acquired:
            resume_node = "%s/resume" % lock.path

            data_node = "%s/data" % lock.path
            (data_value, _) = self.client.get(data_node)
            data = json.loads(data_value.decode(encoding='UTF-8'))
            if data['state'] == 'PAUSED' and self.client.exists(resume_node):
                data['state'] = 'RUNNING'
                self.client.set(data_node, json.dumps(data)
                                .encode(encoding='UTF-8'))
                self.client.delete(resume_node)
                return True
        return False

    def resumeBuildRequest(self, node: str):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        self.log.debug("resumeBuildRequest")
        self.client.ensure_path("%s/resume" % node)

    def shouldResumeBuild(self, lock: Lock) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        return self.client.exists("%s/resume" % lock.path)

    def completeBuild(self, lock: Lock) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        if lock.is_acquired:
            data_node = "%s/data" % lock.path
            (data_value, _) = self.client.get(data_node)
            data = json.loads(data_value.decode(encoding='UTF-8'))
            if data['state'] == 'RUNNING':
                data['state'] = 'COMPLETED'
                self.client.set(data_node, json.dumps(data)
                                .encode(encoding='UTF-8'))
                lock.release()
                return True
        return False

    def cancelBuildRequest(self, node: str):
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        self.log.debug("cancelBuildRequest")
        self.client.ensure_path("%s/cancel" % node)

    def shouldCancelBuild(self, lock: Lock) -> bool:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")
        return self.client.exists("%s/cancel" % lock.path)
