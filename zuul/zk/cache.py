import json
from typing import Any
from typing import Dict
from typing import Optional

from kazoo.protocol.states import ZnodeStat


class ZooKeeperCacheItem(object):
    def __init__(self, content: Dict[str, Any], stat: ZnodeStat):
        self.content = content
        self.stat = stat  # type: ZnodeStat

    def __str__(self):
        return 'ZooKeeperCacheItem(' +\
               'content=' + json.dumps(self.content) + ', ' +\
               'stat=' + str(self.stat) +\
               ')'


class ZooKeeperBuildItem(ZooKeeperCacheItem):
    def __init__(self, path: str, data: Dict[str, str], stat: ZnodeStat):
        super().__init__(data, stat)
        self.path = path  # type: str
        self.params = {}  # type: Dict[str, Any]
        self.params_stat = None  # type: Optional[ZnodeStat]
        self.status = dict(progress=0, total=0)  # type: Dict[str, int]
        self.status_stat = None  # type: Optional[ZnodeStat]
        self.data = {}  # type: Dict[str, Any]
        self.data_stat = None  # type: Optional[ZnodeStat]
        self.result = {}  # type: Dict[str, Any]
        self.result_stat = None  # type: Optional[ZnodeStat]
        self.exception = {}  # type: Dict[str, Any]
        self.exception_stat = None  # type: Optional[ZnodeStat]
        self.cancel = False  # type: bool
        self.resume = False  # type: bool

    @property
    def state(self):
        return self.content['state'] if 'state' in self.content else 'UNKNOWN'

    def __str__(self):
        return 'ZooKeeperBuildItem(' \
               'content=' + json.dumps(self.content) + ', ' +\
               'stat=' + str(self.stat) + ', ' +\
               'params=' + json.dumps(self.params) + ', ' +\
               'params_stat=' + str(self.params_stat) + ', ' +\
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
