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

import json
import logging
import re
import threading
import time
from abc import ABCMeta
from configparser import ConfigParser
from contextlib import contextmanager
from typing import Optional, List, Callable, Generator, Dict, Union, Any

from kazoo.client import KazooClient
from kazoo.exceptions import LockTimeout, ConnectionClosedError, \
    ConnectionLossException
from kazoo.handlers.threading import KazooTimeoutError
from kazoo.protocol.states import KazooState
from kazoo.recipe.lock import Lock

from zuul.lib.config import get_default
from zuul.lib.jsonutil import json_dumps
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
        self.locking_lock: threading.Lock = threading.Lock()
        self._election_locks: Dict[str, Lock] = {}
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

    @property
    def zxid(self) -> int:
        """Current logical timestamp as seen by the Zookeeper cluster."""
        if not self.client:
            raise NoClientException()

        result = self.client.command(b"srvr")
        for line in result.splitlines():
            match = re.match(r"zxid:\s+0x(?P<zxid>[a-f0-9])", line, re.I)
            if match:
                return int(match.group("zxid"), 16)
        raise RuntimeError("Could not find zxid in Zookeeper stat output")

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

    def acquireLock(self, lock: Lock, keep_locked: bool = False,
                    blocking: bool = True, timeout: float = 10.0) -> bool:
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
        :param blocking: Block until lock is obtained or return immediately.
        :param timeout: Timeout to obtain zookeeper lock (default 10 seconds)
        """

        if not keep_locked or not self.locking_lock.locked():
            self.locking_lock.acquire(timeout=timeout)

        try:  # Make sure request does not hang
            return lock.acquire(blocking=blocking, timeout=timeout)
        except LockTimeout:
            self.log.debug("Could not acquire lock %s" % lock.path)
            raise
        finally:
            if not keep_locked and self.locking_lock.locked():
                self.locking_lock.release()

    @contextmanager
    def withLock(self, lock: Lock, blocking: bool = True,
                 timeout: float = 10.0) -> Generator[Lock, None, None]:
        """
        Context manager to use for acquiring ZK locks.

        See "#acquireLock(...)" for details.

        :param lock: ZK lock to acquire
        :param blocking: Block until lock is obtained or return immediately.
        :param timeout: Timeout to obtain zookeeper lock (default 10 seconds)
        """
        locked = False
        try:
            self.acquireLock(lock, blocking=blocking, timeout=timeout)
            locked = True
            self.log.debug("ZK Lock %s locked", lock.path)
            yield lock
        finally:
            if locked:
                self.releaseLock(lock)
            self.log.debug("ZK Lock %s released", lock.path)

    def releaseLock(self, lock: Lock) -> None:
        """
        Releases a lock if it exists.

        This existence check may be necessary in scenarios where a locked node,
        or its parent, is deleted and then unlocked. Unlocking a node will
        create the node again.

        :param lock: Lock to unlock
        """
        if self.client and self.client.exists(lock.path):
            lock.release()

    def election(self, path: str, func: Callable[[], Optional[bool]],
                 repeat: Union[bool, Callable[[], bool]] = False) -> None:
        """
        An extended version of kazoo.recipe.election.Election to provide
        a simple interface for (repeatable) function calls.

        :param path: The election path to use.
        :param func: A function to be called if/when the election is won.
                     The provided function may return a boolean in which case
                     if "repeatable" is True and True is returned the loop will
                     be exited.
        :param repeat: Whether the function should be called in an infinite
                       loop. This may be a function which will be evaluated
                       each loop.
        """
        lock = self._election_locks.get(path)
        if not lock:
            lock = self._election_locks[path] = Lock(self.client, path)

        while True:
            try:
                with lock:
                    # Check in-expensively if we still have the lock
                    # and didn't loose connection
                    while self.connected and lock.is_acquired:
                        interrupt = func()
                        if interrupt is True:
                            return

                        if callable(repeat) and not repeat() \
                                or repeat is False:
                            return

            except ConnectionLossException:
                self.log.warning("Election: Connection to ZK lost")
            except ConnectionClosedError:
                self.log.warning("Election: Connection to ZK closed")

            if callable(repeat) and not repeat() or repeat is False:
                return


class ZooKeeperBase(metaclass=ABCMeta):
    """Base class for components that need to interact with Zookeeper."""

    def __init__(self, client: ZooKeeperClient):
        self.client = client
        self.client.on_connect_listeners.append(self._onConnect)
        self.client.on_disconnect_listeners.append(self._onDisconnect)

    @property
    def kazoo_client(self) -> KazooClient:
        return self.client.kazoo_client

    def _onConnect(self) -> None:
        pass

    def _onDisconnect(self) -> None:
        pass

    @staticmethod
    def _bytes_to_dict(data: bytes) -> Dict[str, Any]:
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def _dict_to_bytes(data: Dict[str, Any]) -> bytes:
        # The custom json_dumps() will also serialize MappingProxyType objects
        return json_dumps(data).encode("utf-8")
