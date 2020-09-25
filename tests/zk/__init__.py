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
import traceback
import uuid
from typing import Dict

from zuul.zk import ZooKeeperClient, ZooKeeperConnection


class TestZooKeeperClient(ZooKeeperClient):
    connections: Dict[str, str] = {}

    def __init__(self):
        super().__init__()
        self._connection_id: str = ''

    def connect(self, *args, **kwargs) -> None:
        if self.client is None:
            stack = "\n".join(traceback.format_stack())
            self._connection_id = uuid.uuid4().hex
            TestZooKeeperClient.connections[self._connection_id] = stack
            self.log.debug("ZK Connecting (%s)", self._connection_id)
        super().connect(*args, **kwargs)

    def disconnect(self):
        if self.client is not None and self.client.connected:
            if self._connection_id in TestZooKeeperClient.connections:
                del TestZooKeeperClient.connections[self._connection_id]
                self.log.debug("ZK Disconnecting (%s)", self._connection_id)
                self._connection_id = ''
        super().disconnect()


class TestZooKeeperConnection(ZooKeeperConnection):
    _zk_client_class = TestZooKeeperClient
