import json
from typing import TYPE_CHECKING, Tuple, Dict, Any, List


class ZooKeeperExecutorsMixin(object):
    """
    Executor relevant methods for ZooKeeper
    """
    ZUUL_EXECUTORS_ROOT = "/zuul/executors"
    ZUUL_EXECUTOR_DEFAULT_ZONE = "default-zone"

    def registerExecutor(self, hostname: str) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        item = dict(
            accepting_work=False,
        )
        value = json.dumps(item).encode(encoding='UTF-8')
        node = self.client.create(path, value, makepath=True, ephemeral=True)
        return node

    def unregisterExecutor(self, hostname: str) -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        self.client.delete(path)

    def setExecutorAcceptingWork(self, hostname: str, accepting_work: bool)\
            -> None:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
        data, stat = self.client.get(path)
        item = json.loads(data.decode('UTF-8'))
        if item['accepting_work'] != accepting_work:
            item['accepting_work'] = accepting_work
            value = json.dumps(item).encode(encoding='UTF-8')
            self.client.set(path, value, version=stat.version)

    def getExecutors(self) -> List[Tuple[str, Dict[str, Any]]]:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        if not self.client:
            raise Exception("No zookeeper client!")

        result = []
        for hostname in self.client.get_children(self.ZUUL_EXECUTORS_ROOT):
            path = '{}/{}'.format(self.ZUUL_EXECUTORS_ROOT, hostname)
            data, _ = self.client.get(path)
            item = json.loads(data.decode('UTF-8'))
            result.append((path, item))
        return result
