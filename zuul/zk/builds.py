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
from functools import total_ordering
from typing import Any, Callable, Dict, Generator, List, Optional

from kazoo.exceptions import LockTimeout, NoNodeError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.cache import TreeCache, TreeEvent
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.zk import ZooKeeperBase, ZooKeeperClient
from zuul.zk.exceptions import BuildNotFound


class BuildState(Enum):
    # Waiting
    REQUESTED = 0
    HOLD = 1
    # InProgress
    RUNNING = 2
    PAUSED = 3
    # Finished
    COMPLETED = 4


class BuildResult(Enum):
    SUCCESS = 0
    # TODO (felix): Not sure what the differnce between CANCELED and ABORTED
    # is, but Zuul uses one and the other in different places.
    CANCELED = 1
    ABORTED = 2
    FAILURE = 3
    RETRY = 4
    RETRY_LIMIT = 5
    ERROR = 6
    MERGER_FAILURE = 7
    POST_FAILURE = 8
    TIMED_OUT = 9
    DISK_FULL = 10


@total_ordering
class BuildItem:
    def __init__(
        self,
        uuid: str,
        state: BuildState,
        precedence: int,
        params: Dict[str, Any],
        zone: str,
        tenant_name: str,
        pipeline_name: str,
    ):
        self.uuid = uuid
        self.state = state
        self.precedence = precedence
        self.params = params
        self.zone = zone
        self.tenant_name = tenant_name
        self.pipeline_name = pipeline_name

        self.result: Optional[BuildResult] = None
        # TODO (felix): Is the progress/status used anywhere? So far I couldn't
        # find anything.
        self.progress: Dict[str, int] = {}
        self.data: Dict[str, Any] = {}
        self.result_data: Dict[str, Any] = {}

        # ZK related data
        self.path: Optional[str] = None
        self._zstat: Optional[ZnodeStat] = None
        self.lock: Optional[Lock] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "state": self.state.name,
            "precedence": self.precedence,
            "params": self.params,
            "zone": self.zone,
            "tenant_name": self.tenant_name,
            "pipeline_name": self.pipeline_name,
            "result": self.result.name if self.result else None,
            "progress": self.progress,
            "data": self.data,
            "result_data": self.result_data,
        }

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        self.uuid = data["uuid"]
        self.state = BuildState[data["state"]]
        self.precedence = data["precedence"]
        self.params = data["params"]
        self.zone = data["zone"]
        self.tenant_name = data["tenant_name"]
        self.pipeline_name = data["pipeline_name"]
        result = data["result"]
        if result:
            self.result = BuildResult[result]
        self.progress = data["progress"]
        self.data = data["data"]
        self.result_data = data["result_data"]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildItem":
        build = cls(
            data["uuid"],
            BuildState[data["state"]],
            data["precedence"],
            data["params"],
            data["zone"],
            data["tenant_name"],
            data["pipeline_name"],
        )

        result = data["result"]
        if result:
            build.result = BuildResult[result]
        build.progress = data["progress"]
        build.data = data["data"]
        build.result_data = data["result_data"]

        return build

    def __lt__(self, other) -> bool:
        # Sort builds by precedence and their creation time in ZooKeeper in
        # ascending order to prevent older builds from starving.
        if self.precedence == other.precedence:
            if self._zstat and other._zstat:
                return self._zstat.ctime < other._zstat.ctime
            # TODO (felix): How to sort if the ctime is not available yet?
            # Not sure if that can even happen as the builds are always looked
            # up from ZK directly. But mypy complains because it could be None.
            return self.uuid < other.uuid
        return self.precedence < other.precedence

    def __eq__(self, other) -> bool:
        same_prec = self.precedence == other.precedence
        if self._zstat and other._zstat:
            same_ctime = self._zstat.ctime == other._zstat.ctime
        else:
            same_ctime = self.uuid == other.uuid

        return same_prec and same_ctime

    def __repr__(self) -> str:
        d = self.to_dict()
        d["path"] = self.path
        d["zstat"] = self._zstat
        return f"<BuildItem {d}>"


class BuildEvent(Enum):
    CREATED = 0
    UPDATED = 1
    RESUMED = 2
    CANCELED = 3
    DELETED = 4


TreeCallback = Callable[[BuildItem, BuildEvent], None]


# TODO (felix): Error handling for the build_queue (mainly ZK and JSONDecode
# errors) when loading and writing data.
class BuildQueue(ZooKeeperBase):
    ROOT = "/zuul/builds"
    LOCK_ROOT = "/zuul/build-locks"
    DEFAULT_ZONE = "default-zone"
    CLEANUP_ELECTION_ROOT = "/zuul/build-cleanup"

    log = logging.getLogger("zuul.zk.builds.BuildQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        zone_filter: Optional[List[str]] = None,
        tree_callback: Optional[TreeCallback] = None,
        use_cache: bool = False,
    ):
        super().__init__(client)

        self.zone_filter = zone_filter
        self.tree_callback = tree_callback
        self.use_cache = use_cache

        self._cached_builds: Dict[str, BuildItem] = {}
        # We register the tree cache listeners per zone, so that an executor
        # only gets events for its zone, but the scheduler could also receive
        # events for different (all) zones.
        self._zone_tree_caches: Dict[str, TreeCache] = {}

        if zone_filter is not None:
            for zone in zone_filter:
                self.register_zone(zone)
        elif self.use_cache:
            # Only register for all zones (which will create ChildWatches) if
            # the cache is enabled.
            self.register_all_zones()

    def _onConnect(self) -> None:
        # Will be called by ZooKeeperBase when the connection is established
        if not self.use_cache:
            return
        for zone_cache in self._zone_tree_caches.values():
            zone_cache.start()

    def _onDisconnect(self) -> None:
        # Will be called by ZooKeeperBase when the connection is closed
        if not self.use_cache:
            return
        for zone_cache in self._zone_tree_caches.values():
            zone_cache.close()

    def register_all_zones(self) -> None:
        # Register a child watch that listens to new zones and automatically
        # registers to them.
        def watch_children(children):
            for zone in children:
                self.register_zone(zone)

        self.kazoo_client.ChildrenWatch(self.ROOT, watch_children)

    def register_zone(self, zone: str) -> None:
        zone_root = "/".join([self.ROOT, zone])
        self.kazoo_client.ensure_path(zone_root)
        # Only create the TreeCache if we have caching enabled
        if zone not in self._zone_tree_caches and self.use_cache:
            zone_cache = TreeCache(self.kazoo_client, zone_root)
            zone_cache.listen_fault(self.cache_fault_listener)
            zone_cache.listen(self.build_cache_listener)
            self._zone_tree_caches[zone] = zone_cache

            # Directly start the cache if we are already connected. This could
            # happen if this method is called via the childwatch after the
            # BuildQueue was initialized.
            if self.client.connected:
                zone_cache.start()

    def _iter_builds(self):
        zones = []
        if self.zone_filter:
            zones = self.zone_filter
        else:
            try:
                # Get all available zones from ZooKeeper
                zones = self.kazoo_client.get_children(self.ROOT)
            except NoNodeError:
                return

        for zone in zones:
            try:
                zone_path = "/".join([self.ROOT, zone])
                builds = self.kazoo_client.get_children(zone_path)
            except NoNodeError:
                # Skip this zone as it doesn't have any builds
                continue

            for uuid in builds:
                build = self.get("/".join([zone_path, uuid]))
                # Do not yield NoneType builds
                if build:
                    yield build

    def in_state(
        self, *states: BuildState
    ) -> Generator[BuildItem, None, None]:
        if not states:
            # If no states are provided, build a tuple containing all available
            # ones to always match. We need a tuple to be compliant to the
            # type of *states above.
            states = tuple(BuildState)

        builds = list(filter(lambda b: b.state in states, self._iter_builds()))

        # Sort the list of builds by precedence and their creation time in
        # ZooKeeper in ascending order to prevent older builds from starving.
        return (b for b in sorted(builds))

    def next(self) -> Generator[BuildItem, None, None]:
        yield from self.in_state(BuildState.REQUESTED)

    def _create_new_state(self) -> BuildState:
        # This is used to override the initial BuildState in the TestBuildQueue
        # for tests which have a hold_jobs_in_queue enabled.
        return BuildState.REQUESTED

    def submit(
        self,
        uuid: str,
        tenant_name: str,
        pipeline_name: str,
        params: Dict[str, Any],
        zone: str,
        precedence: int = 200,
    ) -> str:
        log = get_annotated_logger(self.log, event=None, build=uuid)

        path = "/".join([self.ROOT, zone, uuid])

        build = BuildItem(
            uuid,
            self._create_new_state(),
            precedence,
            params,
            zone,
            tenant_name,
            pipeline_name,
        )
        log.debug("Submitting build to ZooKeeper %s", uuid)

        real_path = self.kazoo_client.create(
            path,
            self._dict_to_bytes(build.to_dict()),
            makepath=True,
        )

        return real_path

    def request_resume(self, build: BuildItem) -> None:
        self.kazoo_client.ensure_path(f"{build.path}/resume")

    def request_cancel(self, build: BuildItem) -> None:
        self.kazoo_client.ensure_path(f"{build.path}/cancel")

    def fulfil_resume(self, build: BuildItem) -> None:
        self.kazoo_client.delete(f"{build.path}/resume")

    def fulfil_cancel(self, build: BuildItem) -> None:
        self.kazoo_client.delete(f"{build.path}/cancel")

    def get(self, path: str, cached: bool = False) -> Optional[BuildItem]:
        if cached:
            # Directly return the BuildItem from the cache (if found)
            uuid = path.split("/")[-1]
            build = self._cached_builds.get(uuid)
            if build:
                return build
        try:
            data, zstat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        content = self._bytes_to_dict(data)

        build = BuildItem.from_dict(content)
        build.path = path
        build._zstat = zstat

        return build

    def refresh(self, build: BuildItem) -> BuildItem:
        data = None
        zstat = None
        try:
            data, zstat = self.kazoo_client.get(build.path)
        except NoNodeError:
            # TODO (felix): If something goes wrong here, should we better just
            # raise the error, so the caller can handle it?
            self.log.error(
                "Could not refresh non-existing build %s", build.path
            )

        if data:
            d = self._bytes_to_dict(data)
        else:
            d = {}

        build.update_from_dict(d)
        build._zstat = zstat

        return build

    def update(self, build: BuildItem) -> None:
        log = get_annotated_logger(self.log, event=None, build=build.uuid)
        log.debug("Updating build in path %s", build.path)

        if build._zstat is None:
            log.debug(
                "Cannot update build %s: Missing version information.",
                build.uuid,
            )
            return
        try:
            zstat = self.kazoo_client.set(
                build.path,
                self._dict_to_bytes(build.to_dict()),
                version=build._zstat.version,
            )
            # Update the zstat on the item after updating the ZK node
            build._zstat = zstat
        except NoNodeError:
            raise BuildNotFound(f"Could not update {build.path}")

    def remove(self, build: BuildItem) -> None:
        try:
            # As the build node might contain children (result, data, ...) we
            # must delete it recursively.
            self.kazoo_client.delete(build.path, recursive=True)
        except NoNodeError:
            # Nothing to do if the node is already deleted
            pass

    def lost_builds(self):
        # Get a list of builds which are running but not locked by any executor
        yield from filter(
            lambda b: not self.is_locked(b), self.in_state(BuildState.RUNNING)
        )

    def lock(
        self, build: BuildItem, blocking: bool = True, timeout: int = None
    ) -> bool:
        # Keep the lock nodes in a different path to keep the build subnode
        # structure clean. Otherwise, the lock node will be in between status,
        # data, result, ...
        path = "/".join([self.LOCK_ROOT, build.uuid])
        have_lock = False
        lock = None
        try:
            lock = Lock(self.kazoo_client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            have_lock = False
            self.log.error("Timeout trying to acquire lock %s", build.path)
        except NoNodeError:
            have_lock = False
            self.log.error("Build not found for locking: %s", build.uuid)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            return False

        build.lock = lock

        # Do an in-place update of the build so we have the latest data.
        self.refresh(build)
        return True

    def is_locked(self, build: BuildItem) -> bool:
        path = "/".join([self.LOCK_ROOT, build.uuid])
        try:
            lock = Lock(self.kazoo_client, path)
            is_locked = len(lock.contenders()) > 0
        except NoNodeError:
            is_locked = False
            self.log.error("Build not found to check lock: %s", build.uuid)

        return is_locked

    def unlock(self, build: BuildItem) -> None:
        if build.lock is None:
            self.log.warning("Build %s does not hold a lock", build)
        else:
            build.lock.release()
            build.lock = None

    def cache_fault_listener(self, e):
        self.log.exception(e)

    def build_cache_listener(self, event):
        try:
            self._build_cache_listener(event)
        except Exception:
            self.log.exception(
                "Exception in build cache update for event: %s", event
            )

    def _build_cache_listener(self, event):
        path = None
        if hasattr(event.event_data, "path"):
            path = event.event_data.path

        # Ignore events without path
        if not path:
            return

        # Ignore root node
        if path == self.ROOT:
            return

        # Ignore lock nodes
        if "__lock__" in path:
            return

        # Ignore unrelated events
        if event.event_type not in (
            TreeEvent.NODE_ADDED,
            TreeEvent.NODE_UPDATED,
            TreeEvent.NODE_REMOVED,
        ):
            return

        self.log.debug("TreeEvent (%s) %s", self._event_type_str(event), path)

        # Split the path into segments to find out the type of event (e.g.
        # a subnode was created or the buildnode itself was touched).
        segments = self._get_segments(path)

        # The segments we are interested in should look something like this:
        # <zone> / <uuid> / [cancel|resume]
        if len(segments) < 2:
            # Ignore events that don't touch a build
            return

        uuid = segments[1]
        action = None
        if len(segments) == 3:
            # The action identifies cancel and resume requests
            action = segments[2]

        # Check if the build is already in our cache
        build = self._cached_builds.get(uuid)

        # Simply the combination of ZK event type, build and action for further
        # usage.
        build_event = None
        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED):
            if event.event_data.data and not action:
                # Action nodes such as resume and cancel don't provide any
                # data.
                if build:
                    build_event = BuildEvent.UPDATED
                else:
                    build_event = BuildEvent.CREATED
            elif action == "cancel":
                build_event = BuildEvent.CANCELED
            elif action == "resume":
                build_event = BuildEvent.RESUMED
        elif event.event_type == TreeEvent.NODE_REMOVED and not action:
            # We will only handle delete events for the build node itself, not
            # any subnode.
            build_event = BuildEvent.DELETED

        self.log.debug(
            "Got cache update event %s for path %s", build_event, path
        )

        if not build_event:
            # If we couldn't map the ZK event, we are not interested in it.
            return

        if build_event == BuildEvent.CREATED:
            # Create a new build from the ZK data and store it in the cache
            d = self._bytes_to_dict(event.event_data.data)
            build = BuildItem.from_dict(d)
            build.path = path
            build.stat = event.event_data.stat
            self._cached_builds[uuid] = build
        elif build_event == BuildEvent.UPDATED:
            if event.event_data.stat.version <= build.stat.version:
                # Don't update to older data
                return
            d = self._bytes_to_dict(event.event_data.data)
            build.update_from_dict(d)
            build._zstat = event.event_data.stat
        elif build_event == BuildEvent.DELETED:
            try:
                build = self._cached_builds[uuid]
                del self._cached_builds[uuid]
            except KeyError:
                # If it's already gone, don't care
                pass

        # Only forward events for existing (or newly created) builds. This is
        # just an additional safeguard. If we haven't got a build yet,
        # something went really wrong.
        if self.tree_callback and build:
            self.tree_callback(build, build_event)

    def _get_segments(self, path: str) -> List[str]:
        if path.startswith(self.ROOT):
            # Normalize the path (remove the root part)
            path = path[len(self.ROOT) + 1:]

        return path.split("/")

    @staticmethod
    def _bytes_to_dict(data: bytes) -> Dict[str, Any]:
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def _dict_to_bytes(data: Dict[str, Any]) -> bytes:
        # The custom json_dumps() will also serialize MappingProxyType objects
        return json_dumps(data).encode("utf-8")

    # TODO (felix): Remove
    @staticmethod
    def _event_type_str(event: TreeEvent) -> str:
        if event.event_type == TreeEvent.NODE_ADDED:
            return "A"
        if event.event_type == TreeEvent.NODE_UPDATED:
            return "U"
        if event.event_type == TreeEvent.NODE_REMOVED:
            return "D"
        return "?"
