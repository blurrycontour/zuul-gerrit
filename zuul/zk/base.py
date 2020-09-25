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
import threading
import time
import traceback
import uuid
from typing import Callable, Dict, List, Optional

from kazoo.client import KazooClient, KazooState
from kazoo.exceptions import LockTimeout
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.recipe.lock import Lock

from zuul.zk.exceptions import NoClientException


class ZooKeeperClient(object):
    log = logging.getLogger("zuul.zk.base.ZooKeeperClient")
    connections: Dict[str, str] = {}

    # Log zookeeper retry every 10 seconds
    retry_log_rate = 10

    def __init__(self):
        '''
        Initialize the ZooKeeper base client object.
        '''
        self.client: Optional[KazooClient] = None
        self.locking_lock = threading.Lock()
        self._last_retry_log: int = 0
        self.on_connect_listeners: List[Callable[[], None]] = []
        self.on_disconnect_listeners = []
        self.connection_id: str = ''
        self.node_watchers: Dict[str, List[Callable[[List[str]], None]]] = {}

    def __str__(self):
        return "<ZooKeeper hash=%s>" % hex(hash(self))

    def _connectionListener(self, state):
        '''
        Listener method for Kazoo connection state changes.

        .. warning:: This method must not block.
        '''
        if state == KazooState.LOST:
            self.log.debug("ZooKeeper connection: LOST")
        elif state == KazooState.SUSPENDED:
            self.log.debug("ZooKeeper connection: SUSPENDED")
        else:
            self.log.debug("ZooKeeper connection: CONNECTED")

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
            stack = "\n".join(traceback.format_stack())
            self.connection_id = uuid.uuid4().hex
            ZooKeeperClient.connections[self.connection_id] = stack
            self.log.debug("ZK Connecting (%s)", self.connection_id)

            args = dict(hosts=hosts, read_only=read_only, timeout=timeout)
            if tls_key:
                args['use_ssl'] = True
                args['keyfile'] = tls_key
                args['certfile'] = tls_cert
                args['ca'] = tls_ca
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
        '''
        Close the ZooKeeper cluster connection.

        You should call this method if you used connect() to establish a
        cluster connection.
        '''
        for listener in self.on_disconnect_listeners:
            listener()

        if self.client is not None and self.client.connected:
            if self.connection_id in ZooKeeperClient.connections:
                del ZooKeeperClient.connections[self.connection_id]
                self.log.debug("ZK Disconnecting (%s)", self.connection_id)
                self.connection_id = ''

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

    def acquireLock(self, lock: Lock, keep_locked: bool = False,
                    timeout: float = 10.0):
        """
        Acquires a ZK lock.

        Acquiring the ZK lock is wrapped with a threading lock. There are 2
        reasons for this "locking" lock:

        1) in production to prevent simultaneous acquisition of ZK locks
           from different threads, which may fail,
        2) in tests to prevent events being popped or pushed while waiting
           for scheduler to settle.

        The parameter keep_locked should be only set to True in the waiting
        to settle. This will allow multiple entry and lock of different
        connection in one scheduler instance from test thread and at the same
        time block lock request from runtime threads.
        If set to True, the lockingLock needs to be unlocked manually
        afterwards.

        :param lock: ZK lock to acquire
        :param keep_locked: Whether to keep the locking (threading) lock locked
        :param timeout: Timeout to obtain zookeeper lock (default 10 seconds)
        """

        if not keep_locked or not self.locking_lock.locked():
            self.locking_lock.acquire()
        locked = False
        try:
            while not locked:
                try:  # Make sure request does not hang
                    lock.acquire(timeout=timeout)
                    locked = True
                except LockTimeout:
                    self.log.debug("Could not acquire lock %s", lock.path)
                    raise
        finally:
            if not keep_locked and self.locking_lock.locked():
                self.locking_lock.release()

    def withLock(self, lock: Lock, timeout=10.0):
        """
        Context manager to use for acquiring ZK locks.

        See "#acquireLock(...)" for details.

        :param lock: ZK lock to acquire
        :param timeout: Timeout to obtain zookeeper lock (default 10 seconds)
        """
        class LockWrapper:
            def __init__(self, client: ZooKeeperClient, l: Lock):
                self.client = client
                self.lock = l
                pass

            def __enter__(self):
                self.client.acquireLock(self.lock, timeout=timeout)
                self.client.log.debug("ZK Lock %s locked", self.lock.path)

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.lock.release()
                self.client.log.debug("ZK Lock %s released", self.lock.path)
        return LockWrapper(self, lock)


class ZooKeeperBase(object):
    def __init__(self, client: ZooKeeperClient):
        self.client = client
        self.client.on_connect_listeners.append(self._onConnect)
        self.client.on_disconnect_listeners.append(self._onDisconnect)

    @property
    def kazoo_client(self) -> KazooClient:
        if not self.client.client:
            raise NoClientException()
        return self.client.client

    def _onConnect(self) -> None:
        pass

    def _onDisconnect(self) -> None:
        pass
