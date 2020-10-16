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
from enum import Enum
from typing import List, Dict, Any

from kazoo.client import KazooClient

from zuul.zk import ZooKeeperBase, ZooKeeperClient, NoClientException


class ZooKeeperComponentState(Enum):
    STOPPED = 0
    RUNNING = 1
    PAUSED = 2


class ZooKeeperComponentReadOnly(object):
    def __init__(self, client: ZooKeeperClient, content: Dict[str, Any]):
        self._client = client
        self._content: Dict[str, Any] = content

    @property
    def kazoo_client(self) -> KazooClient:
        if not self._client.client:
            raise NoClientException()
        return self._client.client

    def __getitem__(self, key: str) -> Any:
        return self._content.get(key)


class ZooKeeperComponent(ZooKeeperComponentReadOnly):
    def __init__(self, client: ZooKeeperClient, component: str, hostname: str,
                 content: Dict[str, Any]):
        self._client = client
        self._component = component
        self._hostname = hostname
        self._path = self._register(content)
        super().__init__(client, content)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == 'state' and isinstance(value, int):
            value = ZooKeeperComponentState(value).name
        if key == 'state' and isinstance(value, ZooKeeperComponentState):
            value = value.name

        self._content[key] = value

        stat = self.kazoo_client.exists(self._path)
        if not stat:  # Re-register, in case connection to zk was interrupted
            self._path = self._register(self._content)
        else:
            content = json.dumps(self._content).encode(encoding='UTF-8')
            self.kazoo_client.set(self._path, content, version=stat.version)

    def _register(self, content: Dict[str, Any]) -> str:
        path = '{}/{}/{}-'.format(ZooKeeperComponentRegistry.ROOT,
                                  self._component, self._hostname)
        return self.kazoo_client.create(
            path, json.dumps(content).encode('utf-8'),
            makepath=True, ephemeral=True, sequence=True)

    def unregister(self):
        self.kazoo_client.delete(self._path)


class ZooKeeperComponentRegistry(ZooKeeperBase):
    """
    Executor relevant methods for ZooKeeper
    """
    ROOT = "/zuul/components"

    log = logging.getLogger("zuul.zk.components.ZooKeeperComponents")

    def all(self, component: str) -> List[ZooKeeperComponentReadOnly]:
        result = []
        path = '{}/{}'.format(self.ROOT, component)
        self.kazoo_client.ensure_path(path)
        for node in self.kazoo_client.get_children(path):
            path = '{}/{}/{}'.format(self.ROOT, component, node)
            data, _ = self.kazoo_client.get(path)
            content = json.loads(data.decode('UTF-8'))
            result.append(ZooKeeperComponentReadOnly(self.client, content))
        return result

    def register(self, component: str, hostname: str) -> ZooKeeperComponent:
        """
        Register component with a hostname

        :param component: Component type
        :param hostname: Hostname
        :return: Path representing the components's ZNode
        """
        return ZooKeeperComponent(self.client, component, hostname, dict(
            hostname=hostname,
            state=ZooKeeperComponentState.STOPPED.name,
        ))
