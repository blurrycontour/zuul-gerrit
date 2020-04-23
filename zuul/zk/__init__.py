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
import configparser

from zuul.zk.connection_event import ZooKeeperConnectionEventMixin
from zuul.lib.config import get_default
from zuul.zk.nodepool import ZooKeeperNodepoolMixin


class ZooKeeper(ZooKeeperConnectionEventMixin, ZooKeeperNodepoolMixin):
    '''
    Class implementing the ZooKeeper interface.

    This class uses the facade design pattern to keep common interaction
    with the ZooKeeper API simple and consistent for the caller, and
    limits coupling between objects. It allows for more complex interactions
    by providing direct access to the client connection when needed (though
    that is discouraged). It also provides for a convenient entry point for
    testing only ZooKeeper interactions.
    '''
    pass


def connect_zookeeper(config: configparser.ConfigParser) -> ZooKeeper:
    zookeeper = ZooKeeper(enable_cache=True)
    zookeeper_hosts = get_default(config, 'zookeeper', 'hosts', None)
    if not zookeeper_hosts:
        raise Exception("The zookeeper hosts config value is required")
    zookeeper_tls_key = get_default(config, 'zookeeper', 'tls_key')
    zookeeper_tls_cert = get_default(config, 'zookeeper', 'tls_cert')
    zookeeper_tls_ca = get_default(config, 'zookeeper', 'tls_ca')
    zookeeper_timeout = float(get_default(config, 'zookeeper',
                                          'session_timeout', 10.0))
    zookeeper.connect(
        hosts=zookeeper_hosts,
        timeout=zookeeper_timeout,
        tls_cert=zookeeper_tls_cert,
        tls_key=zookeeper_tls_key,
        tls_ca=zookeeper_tls_ca)
    return zookeeper
