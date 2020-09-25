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

from zuul.zk import ZooKeeperBuilds, ZooKeeperClient
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.exceptions import NoClientException


class TestZooKeeperBuilds(ZooKeeperBuilds):

    def __init__(self, client: ZooKeeperClient, enable_cache: bool):
        super().__init__(client, enable_cache)
        self.hold_in_queue: bool = False

    def _create_new_state(self) -> str:
        return 'HOLD' if self.hold_in_queue else 'REQUESTED'

    def set_hold_in_queue(self, hold: bool):
        self.hold_in_queue = hold

    def release(self, what: Union[None, str, ZooKeeperBuildItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if not self.kazoo_client:
            raise NoClientException()

        if isinstance(what, ZooKeeperBuildItem):
            what.content['state'] = 'REQUESTED'
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding='UTF-8'),
                version=what.stat.version)
        else:
            for path, cached in self._in_state(lambda s: s == 'HOLD'):
                if not what or re.match(what, cached.content['params']['job']):
                    cached.content['state'] = 'REQUESTED'
                    self.kazoo_client.set(
                        path,
                        json.dumps(cached.content).encode(encoding='UTF-8'),
                        version=cached.stat.version)

    def wait_until_released(self,
                            what: Union[None, str, ZooKeeperBuildItem] = None):
        if not self.kazoo_client:
            raise NoClientException()

        paths: List[str] = []
        if isinstance(what, ZooKeeperBuildItem):
            paths = [what.path]
        else:
            for builds_cache in list(self._builds_cache.values()):
                for path, cached in list(builds_cache.items()):
                    job_name = cached.content['params']['job']
                    if not what or re.match(what, job_name):
                        paths.append(path)

        self.log.debug("Waiting for %s to be released", paths)

        while True:
            on_hold = []
            for builds_cache in list(self._builds_cache.values()):
                for path, cached in list(builds_cache.items()):
                    if path in paths and cached.content['state'] == 'HOLD':
                        on_hold.append(path)
            if len(on_hold) == 0:
                self.log.debug("%s released", what)
                return
            else:
                self.log.debug("Still waiting for %s to be released", on_hold)
                time.sleep(0.1)
