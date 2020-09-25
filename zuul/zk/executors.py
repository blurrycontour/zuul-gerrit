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
from typing import Tuple, Dict, Any, List

from zuul.zk.base import ZooKeeperBase


class ZooKeeperExecutors(ZooKeeperBase):
    """
    Executor relevant methods for ZooKeeper
    """
    ROOT = "/zuul/executors"

    log = logging.getLogger("zuul.zk.executors.ZooKeeperExecutors")

    @property
    def all(self) -> List[Tuple[str, Dict[str, Any]]]:
        result = []
        for hostname in self.kazoo_client.get_children(self.ROOT):
            path = '{}/{}'.format(self.ROOT, hostname)
            data, _ = self.kazoo_client.get(path)
            item = json.loads(data.decode('UTF-8'))
            result.append((path, item))
        return result

    def register(self, hostname: str) -> str:
        """
        Register executor with a hostname

        :param hostname: Hostname to register
        :return: Path represeting the executor's ZNode
        """
        path = '{}/{}'.format(self.ROOT, hostname)
        item = dict(
            accepting_work=False,
        )
        value = json.dumps(item).encode(encoding='UTF-8')
        node = self.kazoo_client.create(path, value, makepath=True,
                                        ephemeral=True)
        return node

    def unregister(self, hostname: str) -> None:
        """
        Unregister executor by a hostname

        :param hostname: Hostname to unregister
        """
        path = '{}/{}'.format(self.ROOT, hostname)
        self.kazoo_client.delete(path)

    def acceptingWork(self, hostname: str, accepting_work: bool) -> None:
        """
        Mark executor as (not-)accepting work.

        :param hostname: Hostname identifying the executor.
        :param accepting_work: Whether accepting work or not
        """
        path = '{}/{}'.format(self.ROOT, hostname)
        data, stat = self.kazoo_client.get(path)
        item = json.loads(data.decode('UTF-8'))
        if item['accepting_work'] != accepting_work:
            item['accepting_work'] = accepting_work
            value = json.dumps(item).encode(encoding='UTF-8')
            self.kazoo_client.set(path, value, version=stat.version)
