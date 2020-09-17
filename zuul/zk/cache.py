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
from typing import Any
from typing import Dict
from typing import Optional

from kazoo.protocol.states import ZnodeStat


class ZooKeeperCacheItem(object):
    def __init__(self, content: Dict[str, Any], stat: ZnodeStat):
        self.content = content
        self.stat: ZnodeStat = stat

    def __str__(self):
        return 'ZooKeeperCacheItem(' +\
               'content=' + json.dumps(self.content) + ', ' +\
               'stat=' + str(self.stat) +\
               ')'


class ZooKeeperBuildItem(ZooKeeperCacheItem):
    def __init__(self, path: str, content: Dict[str, Any], stat: ZnodeStat):
        super().__init__(content, stat)
        self.path: str = path
        self.status: Dict[str, int] = dict(progress=0, total=0)
        self.status_stat: Optional[ZnodeStat] = None
        self.data: Dict[str, Any] = {}
        self.data_stat: Optional[ZnodeStat] = None
        self.result: Dict[str, Any] = {}
        self.result_stat: Optional[ZnodeStat] = None
        self.exception: Dict[str, Any] = {}
        self.exception_stat: Optional[ZnodeStat] = None
        self.cancel: bool = False
        self.resume: bool = False

    @property
    def state(self):
        return self.content['state'] if 'state' in self.content else 'UNKNOWN'

    def __str__(self) -> str:
        return 'ZooKeeperBuildItem(' \
               'content=' + json.dumps(self.content) + ', ' +\
               'stat=' + str(self.stat) + ', ' +\
               'status=' + json.dumps(self.status) + ', ' +\
               'status_stat=' + str(self.status_stat) + ', ' +\
               'data=' + json.dumps(self.data) + ', ' +\
               'data_stat=' + str(self.data_stat) + ', ' +\
               'result=' + json.dumps(self.result) + ', ' +\
               'result_stat=' + str(self.result_stat) + ', ' +\
               'exception=' + json.dumps(self.exception) + ', ' +\
               'exception_stat=' + str(self.exception_stat) + ', ' +\
               'cancel=' + str(self.cancel) + ', ' +\
               'resume=' + str(self.resume) +\
               ')'
