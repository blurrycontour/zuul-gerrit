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
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from kazoo.client import KazooClient
from kazoo.exceptions import (
    BadVersionError,
    LockTimeout,
    NoNodeError,
    NotEmptyError,
)
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.zk import ZooKeeperBase, ZooKeeperClient
from zuul.zk.cache import (
    TreeCacheListener,
    ZooKeeperCacheItem,
    ZooKeeperTreeCacheClient,
)
from zuul.zk.exceptions import BadItemException, LockException


DataType = Union[None, str, List[Any], Dict[str, Any]]


class BuildState(Enum):
    # Waiting
    REQUESTED = 0
    HOLD = -1
    # InProgress
    RUNNING = 2
    PAUSED = 3
    # Finished
    COMPLETED = 4
    CANCELED = 5
    FAILED = 6
    REMOVED = 7
    UNKNOWN = 99


class BuildItem(ZooKeeperCacheItem):
    """
    Build cached Zookeeper item.

    .. attribute:: status
       Content of "status" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: status_stat
       The ZStats of the "status" sub-ZNode.

    .. attribute:: data
       Content of "data" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: data_stat
       The ZStats of the "data" sub-ZNode.

    .. attribute:: result
       Content of "result" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: result_stat
       The ZStats of the "result" sub-ZNode.

    .. attribute:: exception
       Content of "exception" sub-ZNode of the build's ZNode, stored as a
       dictionary.

    .. attribute:: exception_stat
       The ZStats of the "exception" sub-ZNode.

    .. attribute:: cancel
       Whether a "cancel" sub-ZNode exists.

    .. attribute:: resume
       Whether a "resume" sub-ZNode exists.

    """

    def __init__(self, path: str, content: Dict[str, Any], stat: ZnodeStat):
        super().__init__(path, content, stat)
        self.status: Dict[str, int] = dict(progress=0, total=0)
        self.status_stat: Optional[ZnodeStat] = None
        self.data: Dict[str, Any] = {}
        self.data_stat: Optional[ZnodeStat] = None
        self.result: Dict[str, Any] = {}
        self.result_stat: Optional[ZnodeStat] = None
        self.exception: Dict[str, Any] = {}
        self.exception_stat: Optional[ZnodeStat] = None
        self.cancel: bool = False
        self.resume: bool = False

    @property
    def state(self) -> BuildState:
        try:
            return BuildState[self.content["state"]]
        except KeyError:
            return BuildState.UNKNOWN

    @state.setter
    def state(self, state: BuildState):
        self.content["state"] = state.name

    def __str__(self) -> str:
        return (
            "{class_name}("
            "content={content}, "
            "stat={stat}, "
            "status={status}, "
            "status_stat={status_stat}, "
            "data={data}, "
            "data_stat={data_stat}, "
            "result={result}, "
            "result_stat={result_stat}, "
            "exception={exception}, "
            "exception_stat={exception_stat}, "
            "cancel={cancel}, "
            "resume={resume}".format(
                class_name=type(self).__name__,
                content=json.dumps(self.content),
                stat=self.stat,
                status=self.status,
                status_stat=self.status_stat,
                data=json.dumps(self.data),
                data_stat=self.data_stat,
                result=json.dumps(self.result),
                result_stat=self.result_stat,
                exception=json.dumps(self.exception),
                exception_stat=self.exception_stat,
                cancel=self.cancel,
                resume=self.resume,
            )
        )


class ZooKeeperBuildTreeCacheClient(ZooKeeperTreeCacheClient[BuildItem]):
    """
    Zookeeper build tree cache client watching the "/zuul/builds" tree.
    """

    def __init__(
        self,
        client: KazooClient,
        zone: Optional[str] = None,
        listener: Optional[TreeCacheListener] = None,
    ):
        root = (
            "%s/%s" % (ZooKeeperBuilds.ROOT, zone)
            if zone
            else ZooKeeperBuilds.ROOT
        )
        super().__init__(client, root, listener)

    def _createCachedValue(
        self, path: str, content: Union[Dict[str, Any], bool], stat: ZnodeStat
    ) -> BuildItem:
        # A valid build item must contain a non-empty dictionary
        if not content or isinstance(content, bool):
            raise BadItemException()
        return BuildItem(path, content, stat)


class ZooKeeperBuilds(ZooKeeperBase):
    """
    Build relevant methods for ZooKeeper
    """

    ROOT = "/zuul/builds"
    DEFAULT_ZONE = "default-zone"
    CLEANUP_ELECTION_ROOT = "/zuul/build-cleanup"

    log = logging.getLogger("zuul.zk.builds.ZooKeeperBuilds")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)

        self._cache_started: bool = False
        # The cache contains a TreeCacheClient per zone
        self._cache: Dict[str, ZooKeeperBuildTreeCacheClient] = {}
        self._cache_listeners: List[TreeCacheListener] = []
        self._locks: Dict[str, Lock] = {}
        self._register_all_zones: bool = False
        self._to_delete: List[str] = []

        def watchChildren(children):
            if self._register_all_zones:
                for zone in children:
                    self._registerZone(zone)

        self.kazoo_client.ensure_path("%s/%s" % (self.ROOT, self.DEFAULT_ZONE))
        self.kazoo_client.ChildrenWatch(self.ROOT, watchChildren)

        if self.client.connected:
            self._onConnect()
        self.registerZone(self.DEFAULT_ZONE)

    def _onConnect(self) -> None:
        self._cache_started = True
        for cache in self._cache.values():
            cache.start()

    def _onDisconnect(self) -> None:
        self._cache_started = False
        for cache in self._cache.values():
            cache.stop()

    def _createTreeCacheClient(
        self, zone: str
    ) -> ZooKeeperBuildTreeCacheClient:
        return ZooKeeperBuildTreeCacheClient(self.kazoo_client, zone)

    def _cachedItem(self, path: str) -> Optional[BuildItem]:
        """
        Returns a cached item from any cache (in any zone)

        :param path: Path representing the build's node
        :return: Cached build item if any
        """
        for cache in self._cache.values():
            cached: Optional[BuildItem] = cache[path]
            if cached:
                return cached
        return None

    def _uuid(self, path: str) -> Optional[str]:
        cached = self._cachedItem(path)
        return (
            cached.content["uuid"]
            if cached and "uuid" in cached.content
            else None
        )

    def registerCacheListener(self, listener: TreeCacheListener) -> None:
        """
        Registers a cache listener to all build caches of all registered zones.

        :param listener: Listener to register.
        """
        if listener not in self._cache_listeners:
            self._cache_listeners.append(listener)
        for cache in self._cache.values():
            cache.registerListener(listener)

    def registerZone(self, zone: Optional[str] = None) -> None:
        """
        Registers a zone the current instance will listen to. Zone is a prefix
        in a build's path `/zuul/.../{ZONE}/{PRECEDENCE}-{SEQUENCE}`.

        Note: each zone needs to be registered if changes from that zone should
        be listened to. Event the default zone.

        :param zone: Zone to listen to (default zone if not present).
        """
        zone = zone or self.DEFAULT_ZONE
        self.kazoo_client.ensure_path("%s/%s" % (self.ROOT, zone))
        self._registerZone(zone)

    def _registerZone(self, zone: str) -> None:
        if zone not in self._cache:
            cache = self._createTreeCacheClient(zone)
            if self._cache_started:
                cache.start()
            for listener in self._cache_listeners:
                cache.registerListener(listener)
            self._cache[zone] = cache

    def registerAllZones(self) -> None:
        """
        Registers to all currently exisiting zones.

        See :meth:`~zuul.zk.builds.ZooKeeperBuilds.registerZone`.
        """
        self._register_all_zones = True
        for zone in self.kazoo_client.get_children(self.ROOT):
            self.registerZone(zone)

    def _createNewState(self) -> BuildState:
        return BuildState.REQUESTED

    def submit(
        self,
        uuid: str,
        build_set_uuid: str,
        tenant_name: str,
        pipeline_name: str,
        params: Dict[str, Any],
        zone: Optional[str] = None,
        precedence: int = 200,
    ) -> str:
        """
        Submits a new build to the queue. The new build item will be in
        `REQUESTED` state.

        Since there is no build yet, therefore no lock, this method can be
        called from anywhere.

        :param uuid: Build's UUID
        :param params: Build's parameters.
        :param zone: Build zone.
        :param precedence: Precedence (lower number = higher precedence)
        :return: Path representing the submitted build's Znode
        """
        log = get_annotated_logger(self.log, event=None, build=uuid)
        self.registerZone(zone)
        self.kazoo_client.ensure_path(self.ROOT)

        path = "{}/{}/{:0>3}-".format(
            self.ROOT, zone or self.DEFAULT_ZONE, precedence
        )
        content = json_dumps(
            dict(
                uuid=uuid,
                build_set_uuid=build_set_uuid,
                tenant_name=tenant_name,
                pipeline_name=pipeline_name,
                zone=zone or self.DEFAULT_ZONE,
                precedence=precedence,
                state=self._createNewState().name,
                params=params,
            )
        ).encode(encoding="UTF-8")
        log.debug("Submit: Creating node for %s", uuid)
        node = self.kazoo_client.create(
            path, content, sequence=True, makepath=True
        )
        log.debug("Submit: %s created", node)
        return node

    def refresh(self, item: BuildItem) -> None:
        """
        Refreshes the build item by reloading data from Zookeeper.
        Only the build's ZNode will be loaded, all sub-ZNode are ignored
        here. The build's parameters are relevant to reload, all sub-nodes
        are for communication purpose and do not need reloading.

        :param item: Item to reload (in-place)
        """
        log = get_annotated_logger(
            self.log, event=None, build=item.content["uuid"]
        )
        log.debug("Refreshing: %s", item.path)
        # TODO (felix): Catch NoNodeError?
        data, stat = self.kazoo_client.get(item.path)
        content = json.loads(data.decode("UTF-8"))
        item.content = content
        item.stat = stat

    def persist(
        self, item: BuildItem, rescue: bool = False, refresh: bool = True
    ) -> None:
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
        # TODO (felix): Should we also persist the build's subnodes here?
        # I don't understand why we need to differentiate between the build
        # node and it's subnodes on every get/persist/refesh operation. In the
        # end, everything must be up-to-date in ZK, not only parts of the build
        log = get_annotated_logger(
            self.log, event=None, build=item.content["uuid"]
        )
        try:
            log.debug("Persist: %s", item.path)
            self.kazoo_client.set(
                item.path,
                json.dumps(item.content).encode(encoding="UTF-8"),
                version=item.stat.version,
            )
            if refresh:
                self.refresh(item)
        except BadVersionError as e:
            if rescue:
                data, stat = self.kazoo_client.get(item.path)
                content = json.loads(data.decode("UTF-8"))
                log.debug("Persist: %s (refresh)", item.path)
                self.kazoo_client.set(
                    item.path,
                    json.dumps(content).encode(encoding="UTF-8"),
                    version=stat.version,
                )
            else:
                raise e

    def next(self) -> Optional[BuildItem]:
        """
        Retrieves next build in state `REQUESTED` and cleans build started on
        executors which died.

        :param names: Name filter.
        :return: Item or None if no next build item is available
        """
        for path, cached in self.inState(
            BuildState.REQUESTED, BuildState.RUNNING, BuildState.PAUSED,
        ):
            # First filter to significantly lower node count
            if self.kazoo_client.exists(path) and cached.state not in [
                # TODO (felix): Do we need this check if we already checked for
                # the other three result types above? Do we need the cached.state
                # here at all?
                BuildState.HOLD,
                BuildState.COMPLETED,
                BuildState.FAILED,
                BuildState.CANCELED,
                BuildState.REMOVED,
            ]:
                log = get_annotated_logger(
                    self.log, event=None, build=cached.content["uuid"]
                )
                lock = self.getLock(path)
                if lock and cached.state == BuildState.REQUESTED:
                    try:
                        log.debug("Next: Trying to aquire lock")
                        self.client.acquireLock(lock)
                        cached.state = BuildState.RUNNING
                        try:
                            self.persist(cached)
                            log.debug("Next: %s", path)
                            return cached
                        except Exception:
                            self.client.releaseLock(lock)
                            raise
                    except LockTimeout:
                        log.warning(
                            "Next: [%s] Lock could not be acquired!", path
                        )
            # TODO (felix): What about builds where the executor died?
        return None

    def inState(self, *states: BuildState) -> List[Tuple[str, BuildItem]]:
        """
        Gets build in given states ordered by their Znode name
        (`{PRECEDENCE}-{SEQUENCE}`). If no states are provided, all builds will
        be returned.
        """
        if not states:
            # If no states are provided, build a list containing all available
            # ones to always match.
            states = list(BuildState)

        items = []
        for cache in self._cache.values():
            for path, cached in cache.items():
                if cached.state in states:
                    items.append((path, cached))
        # Sort the list by path in ascending order. We only use the last part
        # of the path to ignore the zone as this might lead to inter-zone
        # starving otherwise.
        return sorted(items, key=lambda b: b[0].rsplit("/", 1)[-1])

    def get(self, path: str, cached: bool = False) -> Optional[BuildItem]:
        if cached:
            # Directly return the builditem from the cache (if found)
            for cache in self._cache.values():
                build = cache[path]
                if build:
                    return build

        try:
            data, stat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        # TODO (felix): Serialize BuildItem from json value
        content = json.loads(data.decode("utf-8"))

        build = BuildItem(path, content, stat)
        # TODO (felix): Also get the subnodes (status, data and result)

        try:
            status_data, status_stat = self.kazoo_client.get(f"{path}/status")
            build.status = json.loads(status_data.decode("utf-8"))
        except NoNodeError:
            pass

        try:
            data_data, data_stat = self.kazoo_client.get(f"{path}/data")
            build.data = json.loads(data_data.decode("utf-8"))
        except NoNodeError:
            pass

        try:
            result_data, result_stat = self.kazoo_client.get(f"{path}/result")
            build.result = json.loads(result_data.decode("utf-8"))
        except NoNodeError:
            pass

        return build

    # TODO (felix): Remove. Since we have a get() method now, this shouldn't be
    # used anymore.
    def getCached(self, path: str) -> Optional[BuildItem]:
        """
        Gets a cached build represented by the given "path".

        :param path: Path representing the build's ZNode
        :return: Cached build item if any
        """
        if not path:
            return None
        for cache in self._cache.values():
            cached: Optional[BuildItem] = cache[path]
            if cached:
                return cached
        return None

    # TODO (felix): Remove? I can't find any usage for this one.
    def getAllCached(self, zone: Optional[str] = None) -> List[BuildItem]:
        """
        Returns all cached build items.

        :param zone: Optional zone. If not defined all zones will be traversed.
        :return: List of all build items in selected zones.
        """
        result: List[BuildItem] = []
        for cache_zone, cache in self._cache.items():
            if zone is None or zone == cache_zone:
                result.extend(cache.values())
        return result

    def getLock(self, path: str) -> Optional[Lock]:
        """
        Gets a ZLock object for a build represented by the given "path".
        If a lock for the build was already created the same cached object
        is returned, otherwise a new ZLock object is created and cached.

        :param path: Path representing the build's ZNode
        :return: ZLock for the given build.
        """
        if path and self.kazoo_client.exists(path) and path not in self._locks:
            self.log.debug("GetLock: Creating lock: %s", path)
            self._locks[path] = self.kazoo_client.Lock(path)
        return self._locks.get(path)

    # TODO (felix): I don't fully understand the usage of this function. It
    # does exactly the same like the code parts that acquire the lock for
    # further usage. However, this function just checks if the lock can be
    # acquired and then returns True. Which would mean it actually returns
    # whether the resource can be locked, but not if it was already locked.
    def isLocked(self, path: str) -> bool:
        """
        Checks if the build represented by the given "path" is locked or not.

        :param path: Path representing the build's ZNode
        :return: Whether the build represented by the given "path" is locked
        """
        lock = self.getLock(path)
        self.log.debug(
            "IsLocked: [%s] %s", path, lock.is_acquired if lock else None
        )
        return lock is not None and lock.is_acquired

    def pause(self, path: str) -> bool:
        """
        Pauses a build represented by the given "path".

        :param path: Path representing the build's ZNode
        :return: True if pausing succeeded
        """
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot pause non-existing %s" % path)

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("Pause: %s", path)
        lock = self.getLock(path)
        if lock and lock.is_acquired:
            # Make sure the resume request node does not exist
            resume_node = "%s/resume" % path
            try:
                self.kazoo_client.delete(resume_node)
            except NoNodeError:
                pass

            cached = self._cachedItem(path)
            if cached and cached.state == BuildState.RUNNING:
                cached.state = BuildState.PAUSED
                log.debug("Pause: Updating %s", path)
                self.kazoo_client.set(
                    path,
                    json.dumps(cached.content).encode(encoding="UTF-8"),
                    version=cached.stat.version,
                )
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

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("ResumeRequest: %s/resume", path)
        self.kazoo_client.ensure_path("%s/resume" % path)

    def resumeAttempt(
        self, path: str, action: Callable[[BuildItem], None]
    ) -> bool:
        """
        Tries to resume a build which is in `PAUSED` state and where resume
        was requested using
        :meth:`~zuul.zk.build.ZooKeeperBuilds.resumeRequest`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's node
        :param action: Action to call to actually resume the build
        :return: True if resume attempt was successful
        """
        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot resume non-existing %s", path)
            return False

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("ResumeAttempt: %s", path)
        lock = self.getLock(path)
        cached = self._cachedItem(path)
        if (
            cached
            and lock
            and lock.is_acquired
            and cached.state == BuildState.PAUSED
            and cached.resume
        ):
            cached.state = BuildState.RUNNING
            log.debug("ResumeAttempt: Updating %s", path)
            self.kazoo_client.set(
                path,
                json.dumps(cached.content).encode(encoding="UTF-8"),
                version=cached.stat.version,
            )
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

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("CancelRequest: %s/cancel", path)
        self.kazoo_client.ensure_path("%s/cancel" % path)

    def cancelAttempt(
        self, path: str, action: Callable[[BuildItem], None]
    ) -> bool:
        """
        Tries to cancel a build where cancellation was requested using
        :meth:`~zuul.zk.build.ZooKeeperBuilds.cancelRequest`.

        This method requires a lock on the build's Znode and therefore should
        be called only from the executor server.

        :param path: Path representing the build's Znode
        :param action: Action to call to actually cancel the build
        :return: True if cancel attempt was successful
        """
        if not self.kazoo_client.exists(path):
            self.log.debug("Cannot cancel non-existing %s", path)
            return False

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("CancelAttempt: %s", path)
        lock = self.getLock(path)
        cached = self._cachedItem(path)
        if (
            cached
            and lock
            and lock.is_acquired
            and cached.state in [BuildState.RUNNING, BuildState.PAUSED]
            and cached.cancel
        ):

            cached.state = BuildState.CANCELED
            log.debug("CancelAttempt: Updating %s", path)
            self.kazoo_client.set(
                path,
                json.dumps(cached.content).encode(encoding="UTF-8"),
                version=cached.stat.version,
            )
            log.debug("CancelAttempt: Updated %s", path)
            action(cached)
            self.kazoo_client.delete("%s/cancel" % path)
            return True
        elif not cached:
            log.warning("CancelAttempt: Build node %s not cached!", path)
        return False

    def cleanup(self) -> None:
        """
        Cleans up build with lost executors, build which failed to delete
        in callback or in one of previous cleanup runs.
        """
        self.log.debug("Cleaning up builds...")

        # Cleanup build with lost executors
        # TODO (felix): Just clean up all those nodes which aren't locked in ZK
        # instead of storing those in a local _to_delete list.
        for path, cached in self.inState(
            BuildState.RUNNING, BuildState.PAUSED
        ):
            if self.kazoo_client.exists(path):
                lock = self.getLock(path)
                if lock and not lock.is_acquired:
                    try:
                        # If one can acquire a lock then the executor
                        # which started that build died -> update state
                        # accordingly
                        with self.client.withLock(lock, timeout=1.0):
                            # TODO (felix): picking up a running build from an
                            # executor that died (which is not locked), should
                            # be done in the executor, not here.
                            cached.state = BuildState.FAILED
                            self.kazoo_client.set(
                                path,
                                json.dumps(cached.content).encode(
                                    encoding="UTF-8"
                                ),
                                version=cached.stat.version,
                            )
                            self.log.debug(
                                "Cleanup: %s: Builds marked as FAILED", path
                            )
                        self.remove(path)
                    except NoNodeError:
                        pass
                    except BadVersionError:
                        pass
                    except LockTimeout:
                        pass

        # Cleanup nodes where deletion failed
        for i in range(len(self._to_delete) - 1, -1, -1):
            path = self._to_delete[i]
            self.remove(path)

        # Cleanup nodes where deletion failed and responsible client died
        for path, cached in self.inState(BuildState.REMOVED):
            self.remove(path)

        # Cleanup zombie nodes: empty build nodes. This may happen if a node
        # gets deleted and lock is checked on that node which will create it
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
                                "Cleanup: Zombie removal %s failed!", path
                            )
                except NoNodeError:
                    pass

        # Cleanup lock objects of removed nodes
        locked_paths = list(self._locks.keys())
        for path in locked_paths:
            if not self.kazoo_client.exists(path):
                del self._locks[path]

    def _send(self, path: str, key: str, data: DataType) -> None:
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
        value = (
            data.encode(encoding="UTF-8")
            if isinstance(data, str)
            else json.dumps(data).encode(encoding="UTF-8")
        )
        stat = self.kazoo_client.exists(node)
        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
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
        :param total: Total build to reach
        """
        if not self.kazoo_client.exists(path):
            raise NoNodeError("Cannot set status for non-existing %s" % path)

        lock = self.getLock(path)
        if lock and lock.is_acquired:
            self._send(path, "status", dict(progress=progress, total=total))
        else:
            raise LockException("Lock not acquired!")

    def data(self, path: str, data: DataType) -> None:
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
            self._send(path, "data", data)
        else:
            raise LockException("Lock not acquired!")

    def complete(
        self, path: str, result: DataType = None, success: bool = True
    ) -> bool:
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

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        log.debug("Complete: %s", path)
        lock = self.getLock(path)
        data, stat = self.kazoo_client.get(path)
        content = json.loads(data.decode("UTF-8"))
        if (
            content
            and lock
            and lock.is_acquired
            and content["state"] == BuildState.RUNNING.name
        ):
            content["state"] = (
                BuildState.COMPLETED.name
                if success
                else BuildState.FAILED.name
            )
            try:
                self.kazoo_client.set(
                    path,
                    json.dumps(content).encode(encoding="UTF-8"),
                    version=stat.version,
                )
            except NoNodeError:
                raise NoNodeError("NoNodeError: Could not complete %s" % path)

            self._send(path, "result" if success else "exception", result)
            # The lock shall not be released here (in the executor server)
            # Releasing the lock before sending the result will make the build
            # being subject to cleanup. Releasing the subject after sending
            # the result will introduce a race with removing the node
            # in executor client. Therefore, the executor server obtains the
            # lock, executes the build and sends results. The executor client
            # releases the lock of finished build.
            # TODO (felix): If we server keeps holding the lock, how can the
            # client release it?
            return True
        return False

    def remove(self, path: str) -> None:
        """
        Removes a build's Znode. This should be called after the final
        "result"/"exception" information is transmitted.

        This will also release the lock on the build node.

        This method does not require the caller to hold a lock to the
        build's Znode and can therefore be called from anywhere, e.g.,
        a clean-up job.

        :param path: Path representing the build's ZNode
        """
        if not path or not self.kazoo_client.exists(path):
            self.log.debug("Cannot remove non-existing %s", path)
            if path in self._to_delete:
                self._to_delete.remove(path)
            return

        log = get_annotated_logger(
            self.log, event=None, build=self._uuid(path)
        )
        # TODO (felix): Why are we trying to acquire the lock just to
        # immediately release and delete it?
        lock = self.getLock(path)
        if lock:
            log.debug("Remove: Unlocking %s", path)
            if lock.is_acquired:
                self.client.releaseLock(lock)
                del self._locks[path]
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
            # TODO (felix): Do we need all this "mark for later deletion" part
            # or could we just add a periodic cleanup job that deals with those
            # cases? E.g. in case the executor crashes, marking the build
            # doesn't help much.
            data, stat = self.kazoo_client.get(path)
            content = json.loads(data.decode("UTF-8"))
            # TODO (felix): Seeing all those BuildState.X.name usages now, I
            # come to think if it wouldn't be easier to provide a custom JSON
            # serializer that is able to deal with Enums for the whole ZK
            # serialization part.
            # TODO (felix): Better: Provide a proper Build object with a
            # toDict() and fromDict() method. We could implement the
            # serialization directly in the BuildItem class.
            if content and content["state"] in [
                BuildState.COMPLETED.name,
                BuildState.CANCELED.name,
                BuildState.FAILED.name,
            ]:
                if path not in self._to_delete:
                    self._to_delete.append(path)
                content["state"] = BuildState.REMOVED.name
                try:
                    # Try to mark node as removed in case this client dies
                    # another may pickup the cleanup up
                    self.kazoo_client.set(
                        path,
                        json.dumps(content).encode(encoding="UTF-8"),
                        version=stat.version,
                    )
                    log.info("Remove: Marked as removed: %s", path)
                except Exception:
                    log.exception("Remove: Failed to mark %s as removed", path)
            elif content and content["state"] == BuildState.REMOVED.name:
                if path not in self._to_delete:
                    self._to_delete.append(path)
                log.debug("Remove: Already marked as removed: %s", path)
            elif content:
                log.debug(
                    "Remove: Cannot mark %s in state %s as removed!",
                    path,
                    content["state"],
                )
            else:
                if path in self._to_delete:
                    self._to_delete.remove(path)
                log.debug(
                    "Remove: Could not mark as deleted non existing %s!", path
                )
