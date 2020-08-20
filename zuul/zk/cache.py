from typing import Any
from typing import Dict
from typing import Optional

from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock


class ZooKeeperCacheItem(object):
    def __init__(self, content: Dict[str, Any], stat: ZnodeStat):
        self.content = content
        self.stat = stat  # type: ZnodeStat


class ZooKeeperBuildItem(ZooKeeperCacheItem):
    def __init__(self, data: Dict[str, str], stat: ZnodeStat):
        super().__init__(data, stat)
        self.lock = None  # type: Optional[Lock]
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
