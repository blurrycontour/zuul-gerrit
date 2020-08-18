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
import json
import logging
import threading
import time
from typing import Dict, Callable, List, Optional

from kazoo.client import KazooClient, KazooState
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.recipe.cache import TreeCache

import zuul.model
from zuul.zk.connection_event import ZooKeeperConnectionEventMixin
from zuul.lib.config import get_default
from zuul.zk.builds import ZooKeeperBuildsMixin
from zuul.zk.nodepool import ZooKeeperNodepoolMixin
from zuul.zk.zuul import ZooKeeperZuulMixin


class ZooKeeper(ZooKeeperNodepoolMixin,
                ZooKeeperZuulMixin,
                ZooKeeperConnectionEventMixin,
                ZooKeeperBuildsMixin,
                object):
    '''
    Class implementing the ZooKeeper interface.

    This class uses the facade design pattern to keep common interaction
    with the ZooKeeper API simple and consistent for the caller, and
    limits coupling between objects. It allows for more complex interactions
    by providing direct access to the client connection when needed (though
    that is discouraged). It also provides for a convenient entry point for
    testing only ZooKeeper interactions.
    '''

    log = logging.getLogger("zuul.zk.ZooKeeper")

    # Log zookeeper retry every 10 seconds
    retry_log_rate = 10

    def __init__(self, enable_cache: bool=True):
        '''
        Initialize the ZooKeeper object.

        :param bool enable_cache: When True, enables caching of ZooKeeper
            objects (e.g., HoldRequests).
        '''
        self.client = None  # type: Optional[KazooClient]
        self._became_lost = False  # type: bool
        self._last_retry_log = 0  # type: int
        self.enable_cache = enable_cache  # type: bool

        self.lockingLock = threading.Lock()
        self.event_watchers =\
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]
        # The caching model we use is designed around handing out model
        # data as objects. To do this, we use two caches: one is a TreeCache
        # which contains raw znode data (among other details), and one for
        # storing that data serialized as objects. This allows us to return
        # objects from the APIs, and avoids calling the methods to serialize
        # the data into objects more than once.
        self._hold_request_tree = None  # type: Optional[TreeCache]
        self._cached_hold_requests =\
            {}  # type: Optional[Dict[str, zuul.model.HoldRequest]]

        self.node_watchers =\
            {}  # type: Dict[str, List[Callable[[List[str]], None]]]

    def _dictToStr(self, data):
        return json.dumps(data).encode('utf8')

    def _strToDict(self, data):
        return json.loads(data.decode('utf8'))

    def _connection_listener(self, state):
        '''
        Listener method for Kazoo connection state changes.

        .. warning:: This method must not block.
        '''
        if state == KazooState.LOST:
            self.log.debug("ZooKeeper connection: LOST")
            self._became_lost = True
        elif state == KazooState.SUSPENDED:
            self.log.debug("ZooKeeper connection: SUSPENDED")
        else:
            self.log.debug("ZooKeeper connection: CONNECTED")

    @property
    def connected(self):
        return self.client.state == KazooState.CONNECTED

    @property
    def suspended(self):
        return self.client.state == KazooState.SUSPENDED

    @property
    def lost(self):
        return self.client.state == KazooState.LOST

    @property
    def didLoseConnection(self):
        return self._became_lost

    def resetLostFlag(self):
        self._became_lost = False

    def logConnectionRetryEvent(self):
        now = time.monotonic()
        if now - self._last_retry_log >= self.retry_log_rate:
            self.log.warning("Retrying zookeeper connection")
            self._last_retry_log = now

    def connect(self, hosts: str, read_only: bool=False, timeout: float=10.0,
                tls_cert: Optional[str]=None, tls_key: Optional[str]=None,
                tls_ca: Optional[str]=None):
        '''
        Establish a connection with ZooKeeper cluster.

        Convenience method if a pre-existing ZooKeeper connection is not
        supplied to the ZooKeeper object at instantiation time.

        :param str hosts: Comma-separated list of hosts to connect to (e.g.
            127.0.0.1:2181,127.0.0.1:2182,[::1]:2183).
        :param bool read_only: If True, establishes a read-only connection.
        :param float timeout: The ZooKeeper session timeout, in
            seconds (default: 10.0).
        :param str tls_key: Path to TLS key
        :param str tls_cert: Path to TLS cert
        :param str tls_ca: Path to TLS CA cert
        '''

        if self.client is None:
            args = dict(hosts=hosts, read_only=read_only, timeout=timeout)
            if tls_key:
                args['use_ssl'] = True
                args['keyfile'] = tls_key
                args['certfile'] = tls_cert
                args['ca'] = tls_ca
            self.client = KazooClient(**args)
            self.client.add_listener(self._connection_listener)
            # Manually retry initial connection attempt
            while True:
                try:
                    self.client.start(1)
                    break
                except KazooTimeoutError:
                    self.logConnectionRetryEvent()

        if self.enable_cache:
            self._hold_request_tree = TreeCache(self.client,
                                                self.HOLD_REQUEST_ROOT)
            self._hold_request_tree.listen_fault(self.__cacheFaultListener)
            self._hold_request_tree.listen(self._holdRequestCacheListener)
            self._hold_request_tree.start()

    def __cacheFaultListener(self, e):
        self.log.exception(e)

    def disconnect(self):
        '''
        Close the ZooKeeper cluster connection.

        You should call this method if you used connect() to establish a
        cluster connection.
        '''
        if self._hold_request_tree is not None:
            self._hold_request_tree.close()
            self._hold_request_tree = None

        if self.client is not None and self.client.connected:
            self.client.stop()
            self.client.close()
            self.client = None

    def resetHosts(self, hosts):
        '''
        Reset the ZooKeeper cluster connection host list.

        :param str hosts: Comma-separated list of hosts to connect to (e.g.
            127.0.0.1:2181,127.0.0.1:2182,[::1]:2183).
        '''
        if self.client is not None:
            self.client.set_hosts(hosts=hosts)


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
