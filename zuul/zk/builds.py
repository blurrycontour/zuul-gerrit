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
from zuul.zk.exceptions import LockException, BadItemException


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

    def _createCachedValue(self, path: str,
                           content: Union[Dict[str, Any], bool],
                           stat: ZnodeStat) -> ZooKeeperBuildItem:
        # A valid build item must contain a non-empty dictionary
        if not content or isinstance(content, bool):
            raise BadItemException()
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

        self._enable_cache: bool = enable_cache
        self._builds_cache_started: bool = False
        self._builds_cache: Dict[str, ZooKeeperBuildTreeCacheClient] = {}
        self._builds_cache_listeners: List[L] = []
        self._build_locks: Dict[str, Lock] = {}
        self._to_delete: List[str] = []

    def _onConnect(self) -> None:
        if self._enable_cache:
            self._builds_cache_started = True
            for builds_cache in self._builds_cache.values():
                builds_cache.start()

    def _onDisconnect(self) -> None:
        self._builds_cache_started = False
        for builds_cache in self._builds_cache.values():
            builds_cache.stop()

    def _cachedItem(self, path: str) -> Optional[ZooKeeperBuildItem]:
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

    def _uuid(self, path: str) -> Optional[str]:
        cached = self._cachedItem(path)
        return cached.content['uuid']\
            if cached and 'uuid' in cached.content else None

    def registerCacheListener(self, listener: L) -> None:
        """
        Registers a cache listener to all build caches of all registered zones.

        :param listener: Listener to register.
        """
        if listener not in self._builds_cache_listeners:
            self._builds_cache_listeners.append(listener)
        for cache in self._builds_cache.values():
            cache.registerListener(listener)

    def registerZone(self, zone: Optional[str] = None) -> None:
        """
        Registers a zone the current instance will listen to. Zone is a prefix
        in a build's path `/zuul/builds/{ZONE}/{PRECEDENCE}-{SEQUENCE}`.

        Note: each zone needs to be registered if changes from that zone should
        be listened to. Event the default zone.

        :param zone: Zone to listen to (default zone if not present).
        """
        zone = zone or self.DEFAULT_ZONE
        if self._enable_cache \
                and zone not in self._builds_cache:
            builds_cache = ZooKeeperBuildTreeCacheClient(self.kazoo_client,
                                                         zone)
            if self._builds_cache_started:
                builds_cache.start()
            for listener in self._builds_cache_listeners:
                builds_cache.registerListener(listener)
            self._builds_cache[zone] = builds_cache

    def registerAllZones(self) -> None:
        """
        Registers to all currently exisiting zones.

        See :meth:`~zuul.zk.builds.ZooKeeperBuilds.registerZone`.
        """
        for zone in self.kazoo_client.get_children(self.ROOT):
            self.registerZone(zone)

    def _createNewState(self) -> str:
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
        self.registerZone(zone)
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
            state=self._createNewState(),
            params=params,
        )).encode(encoding='UTF-8')
        log.debug("Submit: Creating node for build %s", uuid)
        node = self.kazoo_client.create(path, content, sequence=True,
                                        makepath=True)
        log.debug("Submit: %s created", node)
        return node

    def refresh(self, item: ZooKeeperBuildItem) -> None:
        """
        Refreshes the build item by reloading data from Zookeeper.
        Only the build's ZNode will be loaded, all sub-ZNode are ignored
        here. The build's parameters are relevant to reload, all sub-nodes
        are for communication purpose and do not need reloading.

        :param item: Item to reload (in-place)
        """
        log = get_annotated_logger(self.log, None, build=item.content['uuid'])
        log.debug("Refreshing: %s", item.path)
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
        log = get_annotated_logger(self.log, None, build=item.content['uuid'])
        try:
            log.debug("Persist: %s", item.path)
            self.kazoo_client.set(item.path, json.dumps(item.content)
                                  .encode(encoding='UTF-8'),
                                  version=item.stat.version)
            if refresh:
                self.refresh(item)
        except BadVersionError as e:
            if rescue:
                data, stat = self.kazoo_client.get(item.path)
                content = json.loads(data.decode('UTF-8'))
                log.debug("Persist: %s (refresh)", item.path)
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
        builds = self.inState(['REQUESTED', 'RUNNING', 'PAUSED'])
        for path, cached in builds:
            # First filter to significantly lower node count
            if self.kazoo_client.exists(path)\
                    and cached.content['state'] not in ['HOLD', 'COMPLETED',
                                                        'FAILED', 'CANCELED',
                                                        'REMOVED']:
                log = get_annotated_logger(self.log, None,
                                           build=cached.content['uuid'])
                lock = self.getLock(path)
                if lock and cached.content['state'] == 'REQUESTED':
                    try:
                        log.debug("Next: Trying to aquire lock")
                        self.client.acquireLock(lock)
                        cached.content['state'] = 'RUNNING'
                        self.persist(cached)
                        if isinstance(cached, ZooKeeperBuildItem):
                            log.debug("Next: %s", path)
                            return cached
                        else:
                            log.debug("Next: Releasing lock")
                            self.client.releaseLock(lock)
                            raise Exception("%s is not a build item" % cached)
                    except LockTimeout:
                        log.warning("Next: [%s] Lock could not be acquired!",
                                    path)
        return None

    def inState(self, state: Union[str, List[str]])\
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

    def getCached(self, path: str) -> Optional[ZooKeeperBuildItem]:
        """
        Gets a cached build represented byt the given "path".

        :param path: Path representing the build's ZNode
        :return: Cached build item if any
        """
        for cache in self._builds_cache.values():
            cached = cache[path] if path else None
            if cached:
                return cached
        return None

    def getLock(self, path: str) -> Optional[Lock]:
        """
        Gets a ZLock object for a build represented by the given "path".
        If a lock for the build was already created the same cached object
        is returned, otherwise a new ZLock object is created and cached.

        :param path: Path representing the build's ZNode
        :return: ZLock for the given build.
        """
        if path and self.kazoo_client.exists(path)\
                and path not in self._build_locks:
            self.log.debug("GetLock: Creating lock: %s", path)
            self._build_locks[path] = self.kazoo_client.Lock(path)
        return self._build_locks.get(path)

    def isLocked(self, path: str) -> bool:
        """
        Checks if the build represented by the given "path" is locked or not.

        :param path: Path representing the build's ZNode
        :return: Whether the build represented by the given "path" is locked
        """
        lock = self.getLock(path)
        self.log.debug("IsLocked: [%s] %s", path,
                       lock.is_acquired if lock else None)
        return lock is not None and lock.is_acquired

    def pause(self, path: str) -> bool:
        """
        Pauses a build represented by the given "path".

        :param path: Path representing the build's ZNode
        :return: True if pausing succeeded
        """
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot pause non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("Pause: %s", path)
        lock = self.getLock(path)
        if lock and lock.is_acquired:
            # Make sure resume request node does not exist
            resume_node = "%s/resume" % path
            if self.kazoo_client.exists(resume_node):
                self.kazoo_client.delete(resume_node)

            cached = self._cachedItem(path)
            if cached and cached.content['state'] == 'RUNNING':
                cached.content['state'] = 'PAUSED'
                log.debug("Pause: Updating %s", path)
                self.kazoo_client.set(path, json.dumps(cached.content)
                                      .encode(encoding='UTF-8'),
                                      version=cached.stat.version)
                log.debug("Pause: Updated %s", path)
                return True
            elif not cached:
                log.warning("Pause: Build node %s not cached!", path)

        log.debug("Pause: Not pausing %s", path)
        return False

    def resumeRequest(self, path: str) -> None:
        """
        Requests resuming a build.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere.

        :param path: Path representing the build's ZNode
        """
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot request resume non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("ResumeRequest: %s/resume", path)
        self.kazoo_client.ensure_path("%s/resume" % path)

    def resumeAttempt(self, path: str,
                      action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to resume a build which is in `PAUSED` state and where resume
        was requested using
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.resumeRequest`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's node
        :param action: Action to call to actually resume the build
        :return: True if resume attempt was successful
        """
        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot resume non-existing %s", path)
            return False

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("ResumeAttempt: %s", path)
        lock = self.getLock(path)
        cached = self._cachedItem(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock and lock.is_acquired\
                and cached.content['state'] == 'PAUSED'\
                and cached.resume:
            cached.content['state'] = 'RUNNING'
            log.debug("ResumeAttempt: Updating %s", path)
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            log.debug("ResumeAttempt: Updated %s", path)
            action(cached)
            self.kazoo_client.delete("%s/resume" % path)
            return True
        elif not cached:
            log.warning("ResumeAttempt: Build node %s not cached!", path)
        return False

    def cancelRequest(self, path: str) -> None:
        """
        Requests canceling a build.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere.

        :param path: Path representing a build Znode
        """
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot request cancel non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("CancelRequest: %s/cancel", path)
        self.kazoo_client.ensure_path("%s/cancel" % path)

    def cancelAttempt(self, path: str,
                      action: Callable[[ZooKeeperBuildItem], None]) -> bool:
        """
        Tries to cancel a build where cancellation was requested using
        :meth:`~zuul.zk.builds.ZooKeeperBuilds.cancelRequest`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's Znode
        :param action: Action to call to actually cancel the build
        :return: True if cancel attempt was successful
        """
        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot cancel non-existing %s", path)
            return False

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("CancelAttempt: %s", path)
        lock = self.getLock(path)
        cached = self._cachedItem(path)
        if cached and isinstance(cached, ZooKeeperBuildItem)\
                and lock and lock.is_acquired\
                and cached.content['state'] in ['RUNNING', 'PAUSED']\
                and cached.cancel:

            cached.content['state'] = 'CANCELED'
            log.debug("CancelAttempt: Updating %s", path)
            self.kazoo_client.set(path, json.dumps(cached.content)
                                  .encode(encoding='UTF-8'),
                                  version=cached.stat.version)
            log.debug("CancelAttempt: Updated %s", path)
            action(cached)
            self.kazoo_client.delete("%s/cancel" % path)
            return True
        elif not cached:
            log.warning("CancelAttempt: Build node %s not cached!", path)
        return False

    def cleanup(self) -> None:
        """
        Cleans up builds with lost executors, builds which failed to delete
        in callback or in one of previous cleanup runs.
        """
        # Cleanup builds with lost executors
        builds = self.inState(['RUNNING', 'PAUSED'])
        self.log.debug("Cleanup: Builds with lost executors")
        for path, cached in builds:
            if self.kazoo_client.exists(path):
                lock = self.getLock(path)
                if lock and not lock.is_acquired:
                    try:
                        # If one can acquire a lock then the executor
                        # which started that build died -> update state
                        # accordingly
                        with self.client.withLock(lock, timeout=1.0):
                            cached.content['state'] = 'FAILED'
                            self.kazoo_client.set(
                                path, json.dumps(cached.content)
                                .encode(encoding='UTF-8'),
                                version=cached.stat.version)
                            self.log.debug(
                                "Cleanup: %s: Builds marked as FAILED", path)
                        self.remove(path)
                    except NoNodeError:
                        pass
                    except BadVersionError:
                        pass
                    except LockTimeout:
                        pass

        # Cleanup nodes where deletion failed
        self.log.debug("Cleanup: Nodes where deletion failed")
        for i in range(len(self._to_delete) - 1, -1, -1):
            path = self._to_delete[i]
            if self.kazoo_client.exists(path):
                try:
                    self.remove(path)
                except NotEmptyError:
                    self.log.exception("Cleanup: Local removal %s failed!",
                                       path)
            else:
                del self._to_delete[i]

        # Cleanup nodes where deletion failed and responsible client died
        self.log.debug("Cleanup: Nodes where deletion failed and dead client")
        builds = self.inState('REMOVED')
        for path, cached in builds:
            if self.kazoo_client.exists(path):
                try:
                    self.remove(path)
                except NotEmptyError:
                    self.log.exception("Cleanup: Removal of marked %s failed!",
                                       path)
            elif path in self._to_delete:
                self._to_delete.remove(path)

        # Cleanup zombie nodes: empty build nodes. This may happen if a node
        # gets deleted and lock is checked on that node which will create it
        self.log.debug("Cleanup: Zombie nodes")
        for zone in self.kazoo_client.get_children(self.ROOT):
            zone_path = "%s/%s" % (self.ROOT, zone)
            for node in self.kazoo_client.get_children(zone_path):
                path = "%s/%s" % (zone_path, node)
                try:
                    data, _ = self.kazoo_client.get(path)
                    if not data:
                        # In general this should not happen, keep warning here
                        # to catch those situations
                        self.log.warning("Cleanup: Found %s zombie node", path)
                        try:
                            self.remove(path)
                        except NotEmptyError:
                            self.log.exception(
                                "Cleanup: Zombie removal %s failed!", path)
                except NoNodeError:
                    pass

        # Cleanup lock objects of removed nodes
        self.log.debug("Cleanup: Lock objects of removed nodes")
        locked_paths = list(self._build_locks.keys())
        for path in locked_paths:
            if not self.kazoo_client.exists(path):
                del self._build_locks[path]

    def _send(self, path: str, key: str, data: Dict[str, Any]):
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
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot send data for non-existing %s" % path)

        node = "%s/%s" % (path, key)
        value = json.dumps(data).encode(encoding='UTF-8')
        stat = self.kazoo_client.exists(node)
        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("Send: [%s] %s", node, data)
        if stat:
            log.debug("Send: [%s] UPDATE", node)
            self.kazoo_client.set(node, value, version=stat.version)
        else:
            try:
                log.debug("Send: [%s] CREATE", node)
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
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot set status for non-existing %s" % path)

        lock = self.getLock(path)
        if lock and lock.is_acquired:
            self._send(path, 'status', dict(progress=progress, total=total))
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
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot set data for non-existing %s" % path)

        lock = self.getLock(path)
        if lock and lock.is_acquired:
            self._send(path, 'data', data)
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
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot complete non-existing %s" % path)

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        log.debug("Complete: %s", path)
        lock = self.getLock(path)
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

            self._send(path, 'result' if success else 'exception', result)
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
        if not path or not self.kazoo_client.exists(path):
            self.log.debug("Cannot remove non-existing %s", path)
            return

        log = get_annotated_logger(self.log, None, build=self._uuid(path))
        lock = self.getLock(path)
        if lock:
            log.debug("Remove: Unlocking %s", path)
            if lock.is_acquired:
                self.client.releaseLock(lock)
                del self._build_locks[path]
        log.debug("Remove: %s", path)

        try:
            self.kazoo_client.delete(path, recursive=True)
            if path in self._to_delete:
                self._to_delete.remove(path)
            log.debug("Remove: Node %s deleted", path)
        except NoNodeError:
            log.debug("Remove: Node %s already deleted", path)
            if path in self._to_delete:
                self._to_delete.remove(path)
        except Exception:
            log.exception("Remove: Failed to remove %s", path)
            # Fallback, if for some reason node could not be removed we
            # try to mark it as removed and remove it later
            data, stat = self.kazoo_client.get(path)
            content = json.loads(data.decode('UTF-8'))
            if content and content['state'] in ['COMPLETED', 'CANCELLED',
                                                'FAILED']:
                if path not in self._to_delete:
                    self._to_delete.append(path)
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
                if path not in self._to_delete:
                    self._to_delete.append(path)
                log.debug("Remove: Already marked as removed: %s", path)
            elif content:
                log.debug("Remove: Cannot mark %s in state %s as removed!",
                          path, content['state'])
            else:
                if path in self._to_delete:
                    self._to_delete.remove(path)
                log.debug("Remove: Could not mark as deleted non existing %s!",
                          path)
