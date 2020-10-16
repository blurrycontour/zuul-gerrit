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
from typing import List, Optional, Union, Dict

from kazoo.recipe.cache import TreeEvent

from zuul.zk import ZooKeeperClient
from zuul.zk.cache import ZooKeeperWorkItem, WorkState
from zuul.zk.work import ZooKeeperWork


class TestZooKeeperWork(ZooKeeperWork):
    log = logging.getLogger("zuul.test.zk.TestZooKeeperWork")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self._hold_in_queue: Dict[str, bool] = {}
        self.history: List[ZooKeeperWorkItem] = []
        self.registerCacheListener(self._historyTreeCacheListener)

    def _historyTreeCacheListener(self, segments: List[str], event: TreeEvent,
                                  item: Optional[ZooKeeperWorkItem]) -> None:

        if event.event_type == TreeEvent.NODE_ADDED\
                and item\
                and len(segments) == 1:
            self.history.append(item)

    def _createNewState(self, name: str) -> WorkState:
        for prefix, hold in self._hold_in_queue.items():
            if name.startswith("%s:" % prefix) and hold:
                return WorkState.HOLD
        return WorkState.REQUESTED

    def setHold(self, prefix: str, hold: bool):
        self._hold_in_queue[prefix] = hold

    def release(self, what: Union[None, str, ZooKeeperWorkItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if isinstance(what, ZooKeeperWorkItem):
            what.state = WorkState.REQUESTED
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding='UTF-8'),
                version=what.stat.version)
        elif what is None:
            for path, cached in self.inState(WorkState.HOLD):
                if cached.name.startswith('merger:'):
                    cached.state = WorkState.REQUESTED
                    self.kazoo_client.set(
                        path,
                        json.dumps(cached.content).encode(encoding='UTF-8'),
                        version=cached.stat.version)
