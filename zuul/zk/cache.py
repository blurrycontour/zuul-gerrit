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
from enum import Enum
from typing import Any, Union, List
from typing import Dict
from typing import Optional

from kazoo.protocol.states import ZnodeStat

DataType = Union[None, str, List[Any], Dict[str, Any]]


class ZooKeeperCacheItem(object):
    """
    A generic zookeeper cached item.

    .. attribute:: path
       Absolute path of the build's ZNode

    .. attribute:: content
       The content of the ZNode, stored as a dictionary

    .. attribute:: stat
       The content's ZStats
    """
    def __init__(self, path: str, content: Dict[str, Any], stat: ZnodeStat):
        self.path: str = path
        self.content: Dict[str, Any] = content
        self.stat: ZnodeStat = stat

    def __str__(self):
        return 'ZooKeeperCacheItem(' +\
               'content=' + json.dumps(self.content) + ', ' +\
               'stat=' + str(self.stat) +\
               ')'


class WorkState(Enum):
    # Waiting
    REQUESTED = 0
    HOLD = -1
    # InProgress
    RUNNING = 2
    PAUSED = 3
    # Finished
    COMPLETED = 4
    CANCELED = 5
    FAILED = 6
    REMOVED = 7
    UNKNOWN = 99


class ZooKeeperWorkItem(ZooKeeperCacheItem):
    """
    Work cached Zookeeper item.

    .. attribute:: name
       Name of the work item.

    .. attribute:: status
       Content of "status" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: status_stat
       The ZStats of the "status" sub-ZNode.

    .. attribute:: data
       Content of "data" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: data_stat
       The ZStats of the "data" sub-ZNode.

    .. attribute:: result
       Content of "result" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: result_stat
       The ZStats of the "result" sub-ZNode.

    .. attribute:: exception
       Content of "exception" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: exception_stat
       The ZStats of the "exception" sub-ZNode.

    .. attribute:: cancel
       Whether a "cancel" sub-ZNode exists.

    .. attribute:: resume
       Whether a "resume" sub-ZNode exists.

    """
    def __init__(self, path: str, name: str, content: Dict[str, Any],
                 stat: ZnodeStat):
        super().__init__(path, content, stat)
        self.name: str = name
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
    def state(self) -> WorkState:
        try:
            return WorkState[self.content['state']]\
                if 'state' in self.content else WorkState.UNKNOWN
        except KeyError:
            return WorkState.UNKNOWN

    @state.setter
    def state(self, state: WorkState):
        self.content['state'] = state.name

    def __str__(self) -> str:
        return "{class_name}(" \
               "name={name}, " \
               "content={content}, " \
               "stat={stat}, " \
               "status={status}, " \
               "status_stat={status_stat}, " \
               "data={data}, " \
               "data_stat={data_stat}, " \
               "result={result}, " \
               "result_stat={result_stat}, " \
               "exception={exception}, " \
               "exception_stat={exception_stat}, " \
               "cancel={cancel}, " \
               "resume={resume}"\
            .format(
                class_name=type(self).__name__,
                name=self.name,
                content=json.dumps(self.content),
                stat=self.stat,
                status=self.status,
                status_stat=self.status_stat,
                data=json.dumps(self.data),
                data_stat=self.data_stat,
                result=json.dumps(self.result),
                result_stat=self.result_stat,
                exception=json.dumps(self.exception),
                exception_stat=self.exception_stat,
                cancel=self.cancel,
                resume=self.resume)
