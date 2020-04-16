from typing import TYPE_CHECKING


class ZooKeeperZuulMixin:
    ZUUL_CONFIG_ROOT = "/zuul"
    # Node content max size: keep ~100kB as a reserve form the 1MB limit
    ZUUL_CONFIG_MAX_SIZE = 1024 * 1024 - 100 * 1024

    def _getZuulNodePath(self, *args: str) -> str:
        return "/".join(filter(lambda s: s is not None and s != '',
                               [self.ZUUL_CONFIG_ROOT] + list(args)))

    def _getConfigPartContent(self, parent, child) -> str:
        if TYPE_CHECKING:  # IDE type checking support
            from zuul.zk import ZooKeeper
            assert isinstance(self, ZooKeeper)

        node = "%s/%s" % (parent, child)
        return self.client.get(node)[0].decode(encoding='UTF-8') \
            if self.client and self.client.exists(node) else ''
