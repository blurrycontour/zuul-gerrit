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
    def kazoo_client(self) -> Optional[KazooClient]:
        return self.client.client

    def disconnect(self):
        self.client.disconnect()


zookeper_class = ZooKeeper


def connect_zookeeper(*args, **kwargs) -> ZooKeeper:
    hosts: Optional[str] = None
    tls_key: Optional[str] = kwargs.get('tls_key')
    tls_cert: Optional[str] = kwargs.get('tls_cert')
    tls_ca: Optional[str] = kwargs.get('tls_ca')
    timeout: float = kwargs.get('timeout', 120.0)
    read_only: bool = kwargs.get('read_only', False)
    enable_cache: bool = kwargs.get('enable_cache', True)

    zookeeper = zookeper_class(enable_cache=enable_cache)

    if len(args) > 0 and isinstance(args[0], configparser.ConfigParser):
        config = args[0]
        hosts = get_default(config, 'zookeeper', 'hosts', None)
        if not hosts:
            raise Exception("The zookeeper hosts config value is required")
        tls_key = get_default(config, 'zookeeper', 'tls_key')
        tls_cert = get_default(config, 'zookeeper', 'tls_cert')
        tls_ca = get_default(config, 'zookeeper', 'tls_ca')
        timeout = float(get_default(config, 'zookeeper', 'session_timeout',
                                    timeout))
    elif len(args) > 0 and isinstance(args[0], str):
        hosts = args[0]
    elif 'hosts' in kwargs and isinstance(kwargs['hosts'], str):
        hosts = kwargs['hosts']

    if not hosts:
        raise Exception("No Zookeeper hosts defined!")

    log = kwargs.get('log', logging.getLogger("zuul.zk.connect_zookeeper"))
    log.debug("Connecting to '%s' ...", hosts)

    zookeeper.client.connect(hosts=hosts,
                             timeout=timeout,
                             tls_key=tls_key,
                             tls_cert=tls_cert,
                             tls_ca=tls_ca,
                             read_only=read_only)
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
