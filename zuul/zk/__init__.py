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
from logging import Logger
from typing import Optional, Any

from kazoo.client import KazooClient
import configparser

from zuul.lib.config import get_default

from zuul.zk.base import ZooKeeperClient
from zuul.zk.builds import ZooKeeperBuilds
from zuul.zk.connection_event import ZooKeeperConnectionEvent
from zuul.zk.executors import ZooKeeperExecutors
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
        self.builds = ZooKeeperBuilds(self.client, enable_cache=enable_cache)
        self.connection_event = ZooKeeperConnectionEvent(self.client)
        self.executors = ZooKeeperExecutors(self.client)
        self.nodepool = ZooKeeperNodepool(self.client,
                                          enable_cache=enable_cache)

    @property
    def kazoo_client(self) -> Optional[KazooClient]:
        return self.client.client

    def connect(self, hosts: str, read_only: bool = False,
                timeout: float = 10.0,
                tls_cert: Optional[str] = None, tls_key: Optional[str] = None,
                tls_ca: Optional[str] = None):
        self.client.connect(hosts, read_only, timeout,
                            tls_cert, tls_key, tls_ca)

    def disconnect(self):
        self.client.disconnect()


def connect_zookeeper(config: configparser.ConfigParser,
                      log: Optional[Logger] = None) -> ZooKeeper:
    zookeeper = ZooKeeper(enable_cache=True)
    zookeeper_hosts = get_default(config, 'zookeeper', 'hosts', None)
    if not zookeeper_hosts:
        raise Exception("The zookeeper hosts config value is required")
    zookeeper_tls_key = get_default(config, 'zookeeper', 'tls_key')
    zookeeper_tls_cert = get_default(config, 'zookeeper', 'tls_cert')
    zookeeper_tls_ca = get_default(config, 'zookeeper', 'tls_ca')
    zookeeper_timeout = float(get_default(config, 'zookeeper',
                                          'session_timeout', 120.0))

    log = log or logging.getLogger("zuul.zk.connect_zookeeper")
    log.debug("Connecting to '%s' ...", zookeeper_hosts)
    zookeeper.connect(
        hosts=zookeeper_hosts,
        timeout=zookeeper_timeout,
        tls_cert=zookeeper_tls_cert,
        tls_key=zookeeper_tls_key,
        tls_ca=zookeeper_tls_ca)
    return zookeeper


class ZooKeeperConnection(object):

    def __init__(self, config: configparser.ConfigParser):
        self.log = logging.getLogger("zuul.zk.ZooKeeperConnection")
        self.config = config
        self.zookeeper: Optional[ZooKeeper] = None

    def __enter__(self) -> ZooKeeper:
        self.log.debug("Establishing connection...")
        self.zookeeper = connect_zookeeper(self.config)
        return self.zookeeper

    def __exit__(self, kind: Any, value: Any, traceback: Optional[Any]):
        self.log.debug("Destroying connection...")
        if self.zookeeper:
            self.zookeeper.disconnect()
