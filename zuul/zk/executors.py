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
from typing import Tuple, Dict, Any, List

from zuul.zk.base import ZooKeeperBase


class ZooKeeperExecutorsMixin(ZooKeeperBase):
    """
    Executor relevant methods for ZooKeeper
    """
    ZUUL_EXECUTORS_ROOT = "/zuul/executors"
    ZUUL_EXECUTOR_DEFAULT_ZONE = "default-zone"

    def registerExecutor(self, hostname: str) -> str:
        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        item = dict(
            accepting_work=False,
        )
        value = json.dumps(item).encode(encoding='UTF-8')
        node = self.client.create(path, value, makepath=True, ephemeral=True)
        return node

    def unregisterExecutor(self, hostname: str) -> None:
        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        self.client.delete(path)

    def setExecutorAcceptingWork(self, hostname: str, accepting_work: bool)\
            -> None:
        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        data, stat = self.client.get(path)
        item = json.loads(data.decode('UTF-8'))
        if item['accepting_work'] != accepting_work:
            item['accepting_work'] = accepting_work
            value = json.dumps(item).encode(encoding='UTF-8')
            self.client.set(path, value, version=stat.version)

    def getExecutors(self) -> List[Tuple[str, Dict[str, Any]]]:
        if not self.client:
            raise Exception("No zookeeper client!")

        result = []
        for hostname in self.client.get_children(self.ZUUL_EXECUTORS_ROOT):
            path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
            data, _ = self.client.get(path)
            item = json.loads(data.decode('UTF-8'))
            result.append((path, item))
        return result
