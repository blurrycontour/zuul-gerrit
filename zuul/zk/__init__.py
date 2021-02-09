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
import time
from abc import ABCMeta
from configparser import ConfigParser
from typing import Optional, Any, List, Callable

from kazoo.client import KazooClient
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.protocol.states import KazooState

from zuul.lib.config import get_default
from zuul.zk.exceptions import NoClientException


class ZooKeeperClient(object):
    log = logging.getLogger("zuul.zk.base.ZooKeeperClient")

    # Log zookeeper retry every 10 seconds
    retry_log_rate = 10

    def __init__(
        self,
        hosts: str,
        timeout: float = 120.0,
        tls_key: Optional[str] = None,
        tls_cert: Optional[str] = None,
        tls_ca: Optional[str] = None,
        read_only: bool = False
    ):
        """
        Initialize the ZooKeeper base client object.
        """
        self.hosts = hosts
        self.timeout = timeout
        self.tls_key = tls_key
        self.tls_cert = tls_cert
        self.tls_ca = tls_ca
        self.read_only = read_only

        self.client: Optional[KazooClient] = None
        self._last_retry_log: int = 0
        self.on_connect_listeners: List[Callable[[], None]] = []
        self.on_disconnect_listeners: List[Callable[[], None]] = []

    @property
    def kazoo_client(self) -> KazooClient:
        if not self.client:
            raise NoClientException()
        return self.client

    def _connectionListener(self, state):
        """
        Listener method for Kazoo connection state changes.

        .. warning:: This method must not block.
        """
        if state == KazooState.LOST:
            self.log.debug("ZooKeeper connection: LOST")
        elif state == KazooState.SUSPENDED:
            self.log.debug("ZooKeeper connection: SUSPENDED")
        else:
            self.log.debug("ZooKeeper connection: CONNECTED")

    @classmethod
    def fromConfig(cls, config: ConfigParser) -> 'ZooKeeperClient':
        hosts = get_default(config, "zookeeper", "hosts", None)
        if not hosts:
            raise Exception("The zookeeper hosts config value is required")
        timeout = float(
            get_default(config, "zookeeper", "session_timeout", 120.0)
        )
        tls_key = get_default(config, "zookeeper", "tls_key")
        tls_cert = get_default(config, "zookeeper", "tls_cert")
        tls_ca = get_default(config, "zookeeper", "tls_ca")

        return cls(
            hosts=hosts,
            timeout=timeout,
            tls_key=tls_key,
            tls_cert=tls_cert,
            tls_ca=tls_ca
        )

    def __enter__(self) -> "ZooKeeperClient":
        self.log.debug("Establishing connection...")
        self.connect()
        return self

    def __exit__(self, kind: Any, value: Any, traceback: Optional[Any]):
        self.log.debug("Destroying connection...")
        self.disconnect()

    @property
    def connected(self):
        return self.client and self.client.state == KazooState.CONNECTED

    @property
    def suspended(self):
        return self.client and self.client.state == KazooState.SUSPENDED

    @property
    def lost(self):
        return not self.client or self.client.state == KazooState.LOST

    def logConnectionRetryEvent(self):
        now = time.monotonic()
        if now - self._last_retry_log >= self.retry_log_rate:
            self.log.warning("Retrying zookeeper connection")
            self._last_retry_log = now

    def connect(self) -> None:
        """
        Establish a connection with ZooKeeper cluster.
        """
        if self.client is None:
            args = dict(
                hosts=self.hosts,
                read_only=self.read_only,
                timeout=self.timeout
            )
            if self.tls_key:
                args["use_ssl"] = True
                args["keyfile"] = self.tls_key
                args["certfile"] = self.tls_cert
                args["ca"] = self.tls_ca
            self.client = KazooClient(**args)
            self.client.add_listener(self._connectionListener)
            # Manually retry initial connection attempt
            while True:
                try:
                    self.client.start(1)
                    break
                except KazooTimeoutError:
                    self.logConnectionRetryEvent()

            for listener in self.on_connect_listeners:
                listener()

    def disconnect(self):
        """
        Close the ZooKeeper cluster connection.

        You should call this method if you used connect() to establish a
        cluster connection.
        """
        for listener in self.on_disconnect_listeners:
            listener()

        if self.client is not None and self.client.connected:
            self.client.stop()
            self.client.close()
            self.client = None

    def resetHosts(self, hosts):
        """
        Reset the ZooKeeper cluster connection host list.

        :param str hosts: Comma-separated list of hosts to connect to (e.g.
            127.0.0.1:2181,127.0.0.1:2182,[::1]:2183).
        """
        if self.client is not None:
            self.client.set_hosts(hosts=hosts)


class ZooKeeperBase(metaclass=ABCMeta):
    """Base class for components that need to interact with Zookeeper."""

    def __init__(self, client: ZooKeeperClient):
        self.client = client
        self.client.on_connect_listeners.append(self._onConnect)
        self.client.on_disconnect_listeners.append(self._onDisconnect)

    @property
    def kazoo_client(self) -> KazooClient:
        return self.client.kazoo_client

    def _onConnect(self):
        pass

    def _onDisconnect(self):
        pass
