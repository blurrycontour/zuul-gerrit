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
import logging
from typing import Optional, Any

from kazoo.client import KazooClient
import configparser

from zuul.lib.config import get_default

from zuul.zk.base import ZooKeeperClient
from zuul.zk.connection_event import ZooKeeperConnectionEvent
from zuul.zk.exceptions import NoClientException
from zuul.zk.nodepool import ZooKeeperNodepool


class ZooKeeper(object):
    """
    Class implementing the ZooKeeper interface.

    This class uses the facade design pattern to keep common interaction
    with the ZooKeeper API simple and consistent for the caller, and
    limits coupling between objects. It allows for more complex interactions
    by providing direct access to the client connection when needed (though
    that is discouraged). It also provides for a convenient entry point for
    testing only ZooKeeper interactions.
    """

    def __init__(self, enable_cache: bool = True):
        """
        Initialize the ZooKeeper object.

        :param bool enable_cache: When True, enables caching of ZooKeeper
            objects (e.g., HoldRequests).
        """
        self.client = ZooKeeperClient()
        self.connection_event = ZooKeeperConnectionEvent(self.client)
        self.nodepool = ZooKeeperNodepool(self.client,
                                          enable_cache=enable_cache)

    @property
    def kazoo_client(self) -> KazooClient:
        if not self.client.client:
            raise NoClientException()
        return self.client.client

    def disconnect(self):
        self.client.disconnect()


zookeeper_class = ZooKeeper


class ZooKeeperConnection(object):

    @classmethod
    def fromConfig(cls, config: configparser.ConfigParser)\
            -> 'ZooKeeperConnection':
        hosts = get_default(config, "zookeeper", "hosts", None)
        if not hosts:
            raise Exception("The zookeeper hosts config value is required")
        timeout = float(get_default(config, "zookeeper", "session_timeout",
                                    120.0))
        tls_key = get_default(config, "zookeeper", "tls_key")
        tls_cert = get_default(config, "zookeeper", "tls_cert")
        tls_ca = get_default(config, "zookeeper", "tls_ca")

        return cls(hosts=hosts, timeout=timeout, tls_key=tls_key,
                   tls_cert=tls_cert, tls_ca=tls_ca)

    def __init__(self, hosts: str, timeout: float = 120.0,
                 tls_key: Optional[str] = None, tls_cert: Optional[str] = None,
                 tls_ca: Optional[str] = None, read_only: bool = False,
                 enable_cache: bool = True):
        self.log = logging.getLogger("zuul.zk.ZooKeeperConnection")
        self._zookeeper: Optional[ZooKeeper] = None
        self._hosts = hosts
        self._timeout = timeout
        self._tls_key = tls_key
        self._tls_cert = tls_cert
        self._tls_ca = tls_ca
        self._read_only = read_only
        self._enable_cache = enable_cache

    def __enter__(self) -> ZooKeeper:
        self.log.debug("Establishing connection...")
        self._zookeeper = self.connect()
        return self._zookeeper

    def __exit__(self, kind: Any, value: Any, traceback: Optional[Any]):
        self.log.debug("Destroying connection...")
        if self._zookeeper:
            self._zookeeper.disconnect()
            self._zookeeper = None

    def connect(self) -> ZooKeeper:
        zookeeper = zookeeper_class(enable_cache=self._enable_cache)
        zookeeper.client.connect(
            hosts=self._hosts,
            timeout=self._timeout,
            tls_key=self._tls_key,
            tls_cert=self._tls_cert,
            tls_ca=self._tls_ca,
            read_only=self._read_only,
        )
        return zookeeper
