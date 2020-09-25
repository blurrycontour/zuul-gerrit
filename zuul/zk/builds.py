# Copyright 2020 BMW Group
#
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
from typing import Optional, Dict, Any, Callable, Tuple, Union, List

from kazoo.client import KazooClient
from kazoo.exceptions import LockTimeout, NoNodeError, BadVersionError, \
    NotEmptyError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.zk import ZooKeeperClient
from zuul.zk.base import ZooKeeperBase
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperTreeCacheClient, L
from zuul.zk.exceptions import NoClientException, LockException


class ZooKeeperBuildTreeCacheClient(
        ZooKeeperTreeCacheClient[ZooKeeperBuildItem]):
    """
    Zookeeper build tree cache client watching the "/zuul/builds" tree.
    """

    def __init__(self, client: KazooClient, zone: Optional[str] = None,
                 multilevel: bool = False,
                 listener: Optional[L] = None):
        root = "%s/%s" % (ZooKeeperBuilds.ROOT, zone)\
            if zone else ZooKeeperBuilds.ROOT
        super().__init__(client, root, multilevel, listener)

    def _create_cached_value(self, path: str, content: Dict[str, Any],
                             stat: ZnodeStat) -> ZooKeeperBuildItem:
        return ZooKeeperBuildItem(path, content, stat)


class ZooKeeperBuilds(ZooKeeperBase):
    """
    Build relevant methods for ZooKeeper
    """
    ROOT = "/zuul/builds"
    DEFAULT_ZONE = "default-zone"

    log = logging.getLogger("zuul.zk.builds.ZooKeeperBuilds")

    def __init__(self, client: ZooKeeperClient, enable_cache: bool):
        super().__init__(client)

        self.__enable_cache: bool = enable_cache
        self.__builds_cache_started: bool = False
        self._builds_cache: Dict[str, ZooKeeperBuildTreeCacheClient] = {}
        self.__builds_cache_listeners: List[L] = []
        self.__build_locks: Dict[str, Lock] = {}
        self.__to_delete: List[str] = []

    def _on_connect(self) -> None:
        if self.__enable_cache:
            self.__builds_cache_started = True
            for builds_cache in self._builds_cache.values():
                builds_cache.start()

    def _on_disconnect(self) -> None:
        self.__builds_cache_started = False
        for builds_cache in self._builds_cache.values():
            builds_cache.stop()

    def __cached_item(self, path: str) -> Optional[ZooKeeperBuildItem]:
        """
        Returns a cached item from any cache (in any zone)

        :param path: Path representing the build's node
        :return: Cached build item if any
        """
        for builds_cache in self._builds_cache.values():
            cached = builds_cache[path]
            if cached:
                return cached
        return None

    def __uuid(self, path: str) -> Optional[str]:
        cached = self.__cached_item(path)
        return cached.content['uuid']\
            if cached and 'uuid' in cached.content else None

    def register_cache_listener(self, listener: L) -> None:
        """
        Registers a cache listener to all build caches of all registered zones.

        :param listener: Listener to register.
        """
        if listener not in self.__builds_cache_listeners:
            self.__builds_cache_listeners.append(listener)
        for cache in self._builds_cache.values():
            cache.register_listener(listener)

    def register_zone(self, zone: Optional[str] = None) -> None:
        """
        Registers a zone the current instance will listen to. Zone is a prefix
        in a build's path `/zuul/builds/{ZONE}/{PRECEDENCE}-{SEQUENCE}`.

        Note: each zone needs to be registered if changes from that zone should
        be listened to. Event the default zone.

        :param zone: Zone to listen to (default zone if not present).
        """
        if not self.kazoo_client:
            raise NoClientException()

        zone = zone or self.DEFAULT_ZONE
        if self.__enable_cache \
                and zone not in self._builds_cache:
            builds_cache = ZooKeeperBuildTreeCacheClient(self.kazoo_client,
                                                         zone)
            if self.__builds_cache_started:
                builds_cache.start()
            for listener in self.__builds_cache_listeners:
                builds_cache.register_listener(listener)
            self._builds_cache[zone] = builds_cache

    def register_all_zones(self) -> None:
        """
        Registers to all currently exisiting zones.

        See :meth:`~zuul.zk.builds.ZooKeeperBuilds.register_zone`.
        """
        if not self.kazoo_client:
            raise NoClientException()

        for zone in self.kazoo_client.get_children(self.ROOT):
            self.register_zone(zone)

    def _create_new_state(self) -> str:
        return 'REQUESTED'

    def submit(self, uuid: str, params: Dict[str, Any], zone: Optional[str],
               precedence: int) -> str:
        """
        Submits a new build to the queue. The new build will be in `REQUESTED`
        state.

        Since there is no build yet, therefore no lock, this method can be
        called from anywhere.

        :param uuid: Build's UUID
        :param params: Build's parameters.
        :param zone: Build zone.
        :param precedence: Precedence (lower number = higher precedence)
        :return: Path representing the submitted build's Znode
        """
        log = get_annotated_logger(self.log, None, build=uuid)
        if not self.kazoo_client:
            raise NoClientException()

        self.register_zone(zone)

        self.kazoo_client.ensure_path(self.ROOT)

        path = '{}/{}/{:0>3}-'.format(self.ROOT,
                                      zone or self.DEFAULT_ZONE,
                                      precedence)
        content = json_dumps(dict(
            uuid=uuid,
            zone=zone or self.DEFAULT_ZONE,
            precedence=precedence,
            # Waiting: REQUESTED, HOLD,
            # InProgress: RUNNING, PAUSED,
            # Finished: COMPLETED, CANCELLED, FAILED, REMOVED
            state=self._create_new_state(),
            params=params,
        )).encode(encoding='UTF-8')
        node = self.kazoo_client.create(path, content, sequence=True,
                                        makepath=True)
        log.debug("Submit: %s", node)
        return node

    def refresh(self, item: ZooKeeperBuildItem) -> None:
        """
        Refreshes the build item by reloading data from Zookeeper.
        Only the build's ZNode will be loaded, all sub-ZNode are ignored
        here. The build's parameters are relevant to reload, all sub-nodes
        are for communication purpose and do not need reloading.

        :param item: Item to reload (in-place)
        """
        if not self.kazoo_client:
            raise NoClientException()

        data, stat = self.kazoo_client.get(item.path)
        content = json.loads(data.decode('UTF-8'))
        item.content = content
        item.stat = stat

    def persist(self, item: ZooKeeperBuildItem,
                rescue: bool = False, refresh: bool = True) -> None:
        """
        Persists given build item to Zookeeper. Only the build's ZNode will
        be persisted, all sub-ZNode are ignored here. The build's parameters
        are relevant to be update, all sub-nodes are for communication purpose
        and do not need to be persisted here.

        :param item: Build item to persist.
        :param rescue: Whether try to rescue in case of bad version error.
        :param refresh: Refresh build item after persisting to ensure fresh
                        cache. Otherwise risk of inconsistency lag.
        """
        if not self.kazoo_client:
            raise NoClientException()

        try:
            self.kazoo_client.set(item.path, json.dumps(item.content)
                                  .encode(encoding='UTF-8'),
                                  version=item.stat.version)
            if refresh:
                self.refresh(item)
        except BadVersionError as e:
            if rescue:
                data, stat = self.kazoo_client.get(item.path)
                content = json.loads(data.decode('UTF-8'))
                self.kazoo_client.set(
                    item.path, json.dumps(content).encode(encoding='UTF-8'),
                    version=stat.version)
            else:
                raise e

    def next(self) -> Optional[ZooKeeperBuildItem]:
        """
        Retrieves next build in state `REQUESTED` and cleans builds started on
        executors which died.

        :return: ZooKeeperBuildItem or None if no next build item is available
        """
        if not self.kazoo_client:
            raise NoClientException()

        builds = self.in_state(['REQUESTED', 'RUNNING', 'PAUSED'])
        for path, cached in builds:
            # First filter to significantly lower node count
            if self.kazoo_client.exists(path)\
                    and cached.content['state'] not in ['HOLD', 'COMPLETED',
                                                        'FAILED', 'CANCELED',
                                                        'REMOVED']:
                log = get_annotated_logger(self.log, None,
                                           build=cached.content['uuid'])
                lock = self.get_lock(path)
                if lock and cached.content['state'] == 'REQUESTED':
                    try:
                        lock.acquire(timeout=10.0)
                        cached.content['state'] = 'RUNNING'
                        self.persist(cached)
                        if isinstance(cached, ZooKeeperBuildItem):
                            log.debug("Next: %s", path)
                            return cached
                        else:
                            lock.release()
                            raise Exception("%s is not a build item" % cached)
                    except LockTimeout:
                        log.warning("Next: [%s] Lock could not be acquired!",
                                    path)
        return None

    def in_state(self, state: Union[str, List[str]])\
            -> List[Tuple[str, ZooKeeperBuildItem]]:
        """
        Gets builds in given state(s) ordered by their Znode name
        (`{PRECEDENCE}-{SEQUENCE}`). A special state "ALL" will match all
        states.

        :param state: One or more state the builds should be in or "ALL" for
                      all states.
        :return: List of builds (tuple path and object) satisfying given state
                 condition.
        """
        states = [state] if isinstance(state, str) and state != 'ALL'\
            else state

        builds = []
        for builds_cache in list(self._builds_cache.values()):
            for path, cached in list(builds_cache.items()):
                if states == 'ALL' or cached.content['state'] in states:
                    builds.append((path, cached))
        # Make sure this is sorted by last element of the path (first item in
        # the tuple) which contains precedence and sequence in ascending order.
        # Last path element instead of whole path is used to ignore zones
        # which may lead to inter-zone starving
        return sorted(builds, key=lambda b: b[0].rsplit("/", 1)[::-1][0])

    def get_cached(self, path: str) -> Optional[ZooKeeperBuildItem]:
        """
        Gets a cached build represented byt the given "path".

        :param path: Path representing the build's ZNode
        :return: Cached build item if any
        """
        for cache in self._builds_cache.values():
            cached = cache[path]
            if cached:
                return cached
        return None

    def get_lock(self, path: str) -> Optional[Lock]:
        """
        Gets a ZLock object for a build represented by the given "path".
        If a lock for the build was already created the same cached object
        is returned, otherwise a new ZLock object is created and cached.

        :param path: Path representing the build's ZNode
        :return: ZLock for the given build.
        """
        if not self.kazoo_client:
            raise NoClientException()

        if self.kazoo_client.exists(path) and path not in self.__build_locks:
            self.__build_locks[path] = self.kazoo_client.Lock(path)
        return self.__build_locks.get(path)

    def is_locked(self, path: str) -> bool:
        """
        Checks if the build represented by the given "path" is locked or not.

        :param path: Path representing the build's ZNode
        :return: Whether the build represented by the given "path" is locked
        """
        if not self.kazoo_client:
            raise NoClientException()

        lock = self.get_lock(path)
        return lock is not None and lock.is_acquired

    def pause(self, path: str) -> bool:
        """
        Pauses a build represented by the given "path".

        :param path: Path representing the build's ZNode
        :return: True if pausing succeeded
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot pause non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        log.debug("Pause: Pausing %s", path)
        lock = self.get_lock(path)
        if lock and lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % path
            if self.kazoo_client.exists(resume_node):
                self.kazoo_client.delete(resume_node)

            cached = self.__cached_item(path)
            if cached and cached.content['state'] == 'RUNNING':
                cached.content['state'] = 'PAUSED'
                self.kazoo_client.set(path, json.dumps(cached.content)
                                      .encode(encoding='UTF-8'),
                                      version=cached.stat.version)
                log.debug("Pause: Paused %s", path)
                return True
            elif not cached:
                raise Exception("Pause: Build node %s not cached!" % path)

        log.debug("Pause: Not pausing %s", path)
        return False

    def resume_request(self, path: str) -> None:
        """
        Requests resuming a build.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere.

        :param path: Path representing the build's ZNode
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot request resume non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        log.debug("ResumeRequest: %s", path)
        self.kazoo_client.ensure_path("%s/resume" % path)

    def resume_attempt(self, path: str,
                       action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to resume a build which is in `PAUSED` state and where resume
        was requested using
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.resume_request`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's node
        :param action: Action to call to actually resume the build
        :return: True if resume attempt was successful
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot resume non-existing %s", path)
            return False

        lock = self.get_lock(path)
        cached = self.__cached_item(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock and lock.is_acquired\
                and cached.content['state'] == 'PAUSED'\
                and cached.resume:
            cached.content['state'] = 'RUNNING'
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            action(cached)
            self.kazoo_client.delete("%s/resume" % path)
            return True
        elif not cached:
            log = get_annotated_logger(self.log, None, build=self.__uuid(path))
            log.warning("ResumeAttempt: Build node %s not cached!", path)
        return False

    def cancel_request(self, path: str) -> None:
        """
        Requests canceling a build.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere.

        :param path: Path representing a build Znode
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot request cancel non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        log.debug("CancelRequest: %s/cancel", path)
        self.kazoo_client.ensure_path("%s/cancel" % path)

    def cancel_attempt(self, path: str,
                       action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to cancel a build where cancellation was requested using
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.cancel_request`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's Znode
        :param action: Action to call to actually cancel the build
        :return: True if cancel attempt was successful
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot cancel non-existing %s", path)
            return False

        lock = self.get_lock(path)
        cached = self.__cached_item(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock and lock.is_acquired\
                and cached.content['state'] in ['RUNNING', 'PAUSED']\
                and cached.cancel:

            log = get_annotated_logger(self.log, None,
                                       build=cached.content['uuid'])
            log.debug("CancelAttempt: Canceling %s", path)
            cached.content['state'] = 'CANCELED'
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            action(cached)
            self.kazoo_client.delete("%s/cancel" % path)
            return True
        return False

    def cleanup(self) -> None:
        """
        Cleans up builds with lost executors, builds which failed to delete
        in callback or in one of previous cleanup runs.
        """
        if not self.kazoo_client:
            raise NoClientException()

        # Cleanup builds with lost executors
        builds = self.in_state(['RUNNING', 'PAUSED'])
        for path, cached in builds:
            if self.kazoo_client.exists(path):
                lock = self.get_lock(path)
                if lock and not lock.is_acquired:
                    try:
                        # If one can acquire a lock then the executor
                        # which started that build died -> update state
                        # accordingly
                        lock.acquire(timeout=1.0)
                        try:
                            cached.content['state'] = 'FAILED'
                            self.kazoo_client.set(
                                path, json.dumps(cached.content)
                                .encode(encoding='UTF-8'),
                                version=cached.stat.version)
                            self.log.debug(
                                "Cleanup: %s: Builds marked as FAILED", path)
                        finally:
                            lock.release()
                        self.remove(path)
                    except NoNodeError:
                        pass
                    except BadVersionError:
                        pass
                    except LockTimeout:
                        pass

        # Cleanup nodes where deletion failed
        for i in range(len(self.__to_delete) - 1, -1, -1):
            path = self.__to_delete[i]
            if self.kazoo_client.exists(path):
                try:
                    self.remove(path)
                except NotEmptyError:
                    self.log.exception("Cleanup: Local removal %s failed!",
                                       path)
            else:
                del self.__to_delete[i]

        # Cleanup nodes where deletion failed and responsible client died
        builds = self.in_state('REMOVED')
        for path, cached in builds:
            if self.kazoo_client.exists(path):
                try:
                    self.remove(path)
                except NotEmptyError:
                    self.log.exception("Cleanup: Removal of marked %s failed!",
                                       path)
            elif path in self.__to_delete:
                self.__to_delete.remove(path)

        # Cleanup lock objects of removed nodes
        locked_paths = list(self.__build_locks.keys())
        for path in locked_paths:
            if not self.kazoo_client.exists(path):
                del self.__build_locks[path]

    def __send(self, path: str, key: str, data: Dict[str, Any]):
        """
        This sends information about the build node identified by "path".

        The information "type" ("data", "status", "result, "exception")
        is the sub-node name. This way it is easy to react on updates of the
        different information types using tree cache listeners.

        This method is intentionally private since it does not check the
        lock but should be called only from the executor server anyway.
        See (:meth:`~zuul.zk.builds.ZooKeeperBuilds.status`,
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.data`,
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.complete`)

        :param path: Path representing the build's ZNode
        :param key: Type of the information
        :param data: Data to transmit
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot send data for non-existing %s" % path)

        node = "%s/%s" % (path, key)
        value = json.dumps(data).encode(encoding='UTF-8')
        stat = self.kazoo_client.exists(node)
        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        log.debug("Sending to %s: %s", node, data)
        if stat:
            self.kazoo_client.set(node, value, version=stat.version)
        else:
            try:
                self.kazoo_client.create(node, value)
            except NoNodeError:
                raise NoNodeError("Could not set data for %s" % node)

    def status(self, path: str, progress: int, total: int) -> None:
        """
        Sends status information of a build.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's ZNode
        :param progress: Current progress
        :param total: Total work to reach
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot set status for non-existing %s" % path)

        lock = self.get_lock(path)
        if lock and lock.is_acquired:
            self.__send(path, 'status', dict(progress=progress, total=total))
        else:
            raise LockException("Lock not acquired!")

    def data(self, path: str, data: Dict[str, Any]) -> None:
        """
        Sends arbitrary information of a build.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's ZNode
        :param data: Data to send
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot set data for non-existing %s" % path)

        lock = self.get_lock(path)
        if lock and lock.is_acquired:
            self.__send(path, 'data', data)
        else:
            raise LockException("Lock not acquired!")

    def complete(self, path: str, result: Dict[str, Any],
                 success: bool = True) -> bool:
        """
        Sends result (or exception) information of a build and changes the
        build's state.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's ZNode
        :param result: Result or exception information
        :param success: Whether build completed successfully or not
        :return: Whether completing the build was successful
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot complete non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        log.debug("Complete: %s", path)
        lock = self.get_lock(path)
        data, stat = self.kazoo_client.get(path)
        content = json.loads(data.decode('UTF-8'))
        if content and lock and lock.is_acquired\
                and content['state'] == 'RUNNING':
            content['state'] = 'COMPLETED' if success else 'FAILED'
            try:
                self.kazoo_client.set(
                    path, json.dumps(content).encode(encoding='UTF-8'),
                    version=stat.version)
            except NoNodeError:
                raise NoNodeError("NoNodeError: Could not complete %s" % path)

            self.__send(path, 'result' if success else 'exception', result)
            # The lock shall not be released here (in the executor server)
            # Releasing the lock before sending the result will make the build
            # being subject to cleanup. Releasing the subject after sending
            # the result will introduce a race with removing the node
            # in executor client. Therefore, the executor server obtains the
            # lock, executes the build and sends results. The executor client
            # releases the lock of finished builds.
            return True
        return False

    def remove(self, path: str) -> None:
        """
        Removes a build's Znode. This should be called after the final
        "result"/"exception" information is transmitted.

        This will also released the lock on the build node.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere, e.g.,
        a clean-up job.

        :param path: Path representing the build's ZNode
        """
        if not self.kazoo_client:
            raise NoClientException()

        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot remove non-existing %s", path)
            return

        log = get_annotated_logger(self.log, None, build=self.__uuid(path))
        lock = self.get_lock(path)
        if lock:
            log.debug("Remove: Unlocking %s", path)
            if lock.is_acquired:
                lock.release()
                del self.__build_locks[path]
        log.debug("Remove: %s", path)

        try:
            self.kazoo_client.delete(path, recursive=True)
            if path in self.__to_delete:
                self.__to_delete.remove(path)
            log.debug("Remove: Node %s deleted", path)
        except NoNodeError:
            log.debug("Remove: Node %s already deleted", path)
            if path in self.__to_delete:
                self.__to_delete.remove(path)
        except Exception:
            log.exception("Remove: Failed to remove %s", path)
            # Fallback, if for some reason node could not be removed we
            # try to mark it as removed and remove it later
            data, stat = self.kazoo_client.get(path)
            content = json.loads(data.decode('UTF-8'))
            if content and content['state'] in ['COMPLETED', 'CANCELLED',
                                                'FAILED']:
                if path not in self.__to_delete:
                    self.__to_delete.append(path)
                content['state'] = 'REMOVED'
                try:
                    # Try to mark node as removed in case this client dies
                    # another may pickup the cleanup up
                    self.kazoo_client.set(
                        path, json.dumps(content).encode(encoding='UTF-8'),
                        version=stat.version)
                    log.info("Remove: Marked as removed: %s", path)
                except Exception:
                    log.exception("Remove: Failed to mark %s as removed", path)
            elif content and content['state'] == 'REMOVED':
                if path not in self.__to_delete:
                    self.__to_delete.append(path)
                log.debug("Remove: Already marked as removed: %s", path)
            elif content:
                log.debug("Remove: Cannot mark %s in state %s as removed!",
                          path, content['state'])
            else:
                if path in self.__to_delete:
                    self.__to_delete.remove(path)
                log.debug("Remove: Could not mark as deleted non existing %s!",
                          path)
