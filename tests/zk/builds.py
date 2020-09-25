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
import re
import time
from typing import Union, List

from zuul.zk import ZooKeeperClient
from zuul.zk.builds import ZooKeeperBuilds, ZooKeeperBuildItem
from zuul.zk.work import WorkState


class TestZooKeeperBuilds(ZooKeeperBuilds):

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self.hold_in_queue: bool = False

    def _createNewState(self, name: str) -> WorkState:
        return WorkState.HOLD if self.hold_in_queue else WorkState.REQUESTED

    def setHoldInQueue(self, hold: bool):
        self.hold_in_queue = hold

    def release(self, what: Union[None, str, ZooKeeperBuildItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if isinstance(what, ZooKeeperBuildItem):
            what.state = WorkState.REQUESTED
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding='UTF-8'),
                version=what.stat.version)
        else:
            for path, cached in self.inState(WorkState.HOLD):
                if not what or re.match(what, cached.content['params']['job']):
                    cached.state = WorkState.REQUESTED
                    self.kazoo_client.set(
                        path,
                        json.dumps(cached.content).encode(encoding='UTF-8'),
                        version=cached.stat.version)

    def waitUntilReleased(self,
                          what: Union[None, str, ZooKeeperBuildItem] = None):
        paths: List[str] = []
        if isinstance(what, ZooKeeperBuildItem):
            paths = [what.path]
        else:
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    job_name = cached.content['params']['job']
                    if not what or re.match(what, job_name):
                        paths.append(path)

        self.log.debug("Waiting for %s to be released", paths)

        while True:
            on_hold = []
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    if path in paths and cached.state == WorkState.HOLD:
                        on_hold.append(path)
            if len(on_hold) == 0:
                self.log.debug("%s released", what)
                return
            else:
                self.log.debug("Still waiting for %s to be released", on_hold)
                time.sleep(0.1)
