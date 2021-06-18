# Copyright 2021 BMW Group
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
from contextlib import suppress
from enum import Enum

from kazoo.exceptions import LockTimeout, NoNodeError
from kazoo.protocol.states import EventType
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.model import BuildRequest
from zuul.zk import ZooKeeperSimpleBase
from zuul.zk.exceptions import BuildRequestNotFound
from zuul.zk import sharding


class BuildRequestEvent(Enum):
    CREATED = 0
    UPDATED = 1
    RESUMED = 2
    CANCELED = 3
    DELETED = 4


class ExecutorApi(ZooKeeperSimpleBase):

    BUILD_REQUEST_ROOT = "/zuul/build-requests"
    LOCK_ROOT = "/zuul/build-request-locks"

    log = logging.getLogger("zuul.zk.executor.ExecutorApi")

    def __init__(self, client, zone_filter=None,
                 build_request_callback=None,
                 build_event_callback=None):
        super().__init__(client)

        self.zone_filter = zone_filter
        self._watched_zones = set()
        self.build_request_callback = build_request_callback
        self.build_event_callback = build_event_callback

        # path -> build request
        self._cached_build_requests = {}

        if zone_filter is None:
            self.registerAllZones()
        else:
            for zone in zone_filter:
                self.registerZone(zone)

    @property
    def initial_state(self):
        # This supports holding build requests in tests
        return BuildRequest.REQUESTED

    def _getZoneRoot(self, zone):
        if zone is None:
            return "/".join([self.BUILD_REQUEST_ROOT, 'unzoned'])
        else:
            return "/".join([self.BUILD_REQUEST_ROOT, 'zones', zone])

    def registerZone(self, zone):
        if zone in self._watched_zones:
            return
        zone_root = self._getZoneRoot(zone)
        self.log.debug("Registering for zone %s at %s", zone, zone_root)
        self.kazoo_client.ensure_path(zone_root)

        self.kazoo_client.ChildrenWatch(
            zone_root, self._makeBuildRequestWatcher(zone_root),
            send_event=True
        )
        self._watched_zones.add(zone)

    def registerAllZones(self):
        self.kazoo_client.ensure_path(self.BUILD_REQUEST_ROOT)

        # Register a child watch that listens to new zones and automatically
        # registers to them.
        def watch_zones(children):
            for zone in children:
                self.registerZone(zone)

        zones_root = "/".join([self.BUILD_REQUEST_ROOT, 'zones'])
        self.kazoo_client.ensure_path(zones_root)
        self.kazoo_client.ChildrenWatch(zones_root, watch_zones)
        self.registerZone(None)

    def _makeBuildStateWatcher(self, path):
        def watch(data, stat, event=None):
            return self._watchBuildState(path, data, stat, event)
        return watch

    def _watchBuildState(self, path, data, stat, event=None):
        if not event or event.type == EventType.CHANGED:
            # As we already get the data and the stat value, we can directly
            # use it without asking ZooKeeper for the data again.
            content = self._bytesToDict(data)
            if not content:
                return

            # We need this one for the HOLD -> REQUESTED check further down
            old_build_request = self._cached_build_requests.get(path)

            build_request = BuildRequest.fromDict(content)
            build_request.path = path
            build_request._zstat = stat
            self._cached_build_requests[path] = build_request

            # NOTE (felix): This is a test-specific condition: For test cases
            # which are using hold_jobs_in_queue the state change on the build
            # request from HOLD to REQUESTED is done outside of the executor.
            # Thus, we must also set the wake event (the callback) so the
            # executor can pick up those builds after they are released. To not
            # cause a thundering herd problem in production for each cache
            # update, the callback is only called under this very specific
            # condition that can only occur in the tests.
            if (
                self.build_request_callback
                and old_build_request
                and old_build_request.state == BuildRequest.HOLD
                and build_request.state == BuildRequest.REQUESTED
            ):
                self.build_request_callback()

        elif event.type == EventType.DELETED:
            build_request = self._cached_build_requests.get(path)
            with suppress(KeyError):
                del self._cached_build_requests[path]

            if build_request and self.build_event_callback:
                self.build_event_callback(
                    build_request, BuildRequestEvent.DELETED
                )

            # Return False to stop the datawatch as the build got deleted.
            return False

    def _makeBuildRequestWatcher(self, path):
        def watch(build_requests, event=None):
            return self._watchBuildRequests(path, build_requests, event)
        return watch

    def _watchBuildRequests(self, path, build_requests, event=None):
        # The build_requests list always contains all active children. Thus, we
        # first have to find the new ones by calculating the delta between the
        # build_requests list and our current cache entries.
        # NOTE (felix): We could also use this list to determine the deleted
        # build requests, but it's easier to do this in the DataWatch for the
        # single build request instead. Otherwise we have to deal with race
        # conditions between the children and the data watch as one watch might
        # update a cache entry while the other tries to remove it.

        build_request_paths = {
            f"{path}/{uuid}" for uuid in build_requests
        }

        new_build_requests = build_request_paths - set(
            self._cached_build_requests.keys()
        )

        for req_path in new_build_requests:
            self.kazoo_client.DataWatch(req_path,
                                        self._makeBuildStateWatcher(req_path))

        # Notify the user about new build requests if a callback is provided,
        # but only if there are new requests (we don't want to fire on the
        # initial callback from kazoo from registering the datawatch).
        if new_build_requests and self.build_request_callback:
            self.build_request_callback()

    def _iterBuildRequests(self):
        # As the entries in the cache dictionary are added and removed via
        # data and children watches, we can't simply iterate over it in here,
        # as the values might change during iteration.
        for key in list(self._cached_build_requests.keys()):
            try:
                build_request = self._cached_build_requests[key]
            except KeyError:
                continue
            yield build_request

    def inState(self, *states):
        if not states:
            # If no states are provided, build a tuple containing all available
            # ones to always match. We need a tuple to be compliant to the
            # type of *states above.
            states = BuildRequest.ALL_STATES

        build_requests = list(
            filter(lambda b: b.state in states, self._iterBuildRequests())
        )

        # Sort the list of builds by precedence and their creation time in
        # ZooKeeper in ascending order to prevent older builds from starving.
        return (b for b in sorted(build_requests))

    def next(self):
        yield from self.inState(BuildRequest.REQUESTED)

    def submit(self, uuid, tenant_name, pipeline_name, params, zone,
               event_id, precedence=200):
        log = get_annotated_logger(self.log, event=None, build=uuid)

        zone_root = self._getZoneRoot(zone)
        path = "/".join([zone_root, uuid])

        build_request = BuildRequest(
            uuid,
            self.initial_state,
            precedence,
            zone,
            tenant_name,
            pipeline_name,
            event_id,
        )

        log.debug("Submitting build request to ZooKeeper %s", build_request)

        self.kazoo_client.ensure_path(zone_root)
        tr = self.kazoo_client.transaction()

        tr.create(
            path,
            self._dictToBytes(build_request.toDict()),
        )
        params_path = self._getParamsPath(path)
        tr.create(params_path)
        params_path = '/'.join([params_path, 'seq'])
        with sharding.BufferedShardWriter(tr, params_path) as stream:
            stream.write(self._dictToBytes(params))
        self.client.commitTransaction(tr)
        return path

    # We use child nodes here so that we don't need to lock the build
    # request node.
    def requestResume(self, build_request):
        self.kazoo_client.ensure_path(f"{build_request.path}/resume")

    def requestCancel(self, build_request):
        self.kazoo_client.ensure_path(f"{build_request.path}/cancel")

    def fulfillResume(self, build_request):
        self.kazoo_client.delete(f"{build_request.path}/resume")

    def fulfillCancel(self, build_request):
        self.kazoo_client.delete(f"{build_request.path}/cancel")

    def update(self, build_request):
        log = get_annotated_logger(
            self.log, event=None, build=build_request.uuid
        )
        log.debug("Updating build request %s", build_request)

        if build_request._zstat is None:
            log.debug(
                "Cannot update build request %s: Missing version information.",
                build_request.uuid,
            )
            return
        try:
            zstat = self.kazoo_client.set(
                build_request.path,
                self._dictToBytes(build_request.toDict()),
                version=build_request._zstat.version,
            )
            # Update the zstat on the item after updating the ZK node
            build_request._zstat = zstat
        except NoNodeError:
            raise BuildRequestNotFound(
                f"Could not update {build_request.path}"
            )

    def get(self, path):
        """Get a build request

        Note: do not mix get with iteration; iteration returns cached
        BuildRequests while get returns a newly created object each
        time.  If you lock a BuildRequest, you must use the same
        object to unlock it.

        """

        try:
            data, zstat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        content = self._bytesToDict(data)

        build_request = BuildRequest.fromDict(content)
        build_request.path = path
        build_request._zstat = zstat

        return build_request

    def remove(self, build_request):
        try:
            # As the build node might contain children (result, data, ...) we
            # must delete it recursively.
            self.kazoo_client.delete(build_request.path, recursive=True)
        except NoNodeError:
            # Nothing to do if the node is already deleted
            pass
        try:
            # Delete the lock parent node as well.
            path = "/".join([self.LOCK_ROOT, build_request.uuid])
            self.kazoo_client.delete(path, recursive=True)
        except NoNodeError:
            pass

    def _watchBuildEvents(self, actions, event=None):
        if event is None:
            return

        for action in actions:
            build_event = None
            if action == "cancel":
                build_event = BuildRequestEvent.CANCELED
            elif action == "resume":
                build_event = BuildRequestEvent.RESUMED

            if build_event and self.build_event_callback:
                build_request = self._cached_build_requests.get(event.path)
                self.build_event_callback(build_request, build_event)

    def lock(self, build_request, blocking=True, timeout=None):
        # Keep the lock nodes in a different path to keep the build request
        # subnode structure clean. Otherwise, the lock node will be in between
        # the cancel and resume requests.
        path = "/".join([self.LOCK_ROOT, build_request.uuid])
        have_lock = False
        lock = None
        try:
            lock = Lock(self.kazoo_client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            have_lock = False
            self.log.error(
                "Timeout trying to acquire lock: %s", build_request.uuid
            )

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            return False

        if not self.kazoo_client.exists(build_request.path):
            lock.release()
            self.log.error(
                "Build not found for locking: %s", build_request.uuid
            )

            # We may have just re-created the lock parent node just
            # after the scheduler deleted it; therefore we should
            # (re-) delete it.
            try:
                # Delete the lock parent node as well.
                path = "/".join([self.LOCK_ROOT, build_request.uuid])
                self.kazoo_client.delete(path, recursive=True)
            except NoNodeError:
                pass

            return False

        build_request.lock = lock

        # Create the children watch to listen for cancel/resume actions on this
        # build request.
        self.kazoo_client.ChildrenWatch(
            build_request.path, self._watchBuildEvents, send_event=True
        )
        return True

    def unlock(self, build_request):
        if build_request.lock is None:
            self.log.warning(
                "BuildRequest %s does not hold a lock", build_request
            )
        else:
            build_request.lock.release()
            build_request.lock = None

    def isLocked(self, build_request):
        path = "/".join([self.LOCK_ROOT, build_request.uuid])
        try:
            lock = Lock(self.kazoo_client, path)
            is_locked = len(lock.contenders()) > 0
        except NoNodeError:
            is_locked = False
            self.log.error(
                "BuildReqeust not found to check lock: %s", build_request.uuid
            )

        return is_locked

    def lostBuildRequests(self):
        # Get a list of builds which are running but not locked by any executor
        yield from filter(
            lambda b: not self.isLocked(b),
            self.inState(BuildRequest.RUNNING, BuildRequest.PAUSED),
        )

    @staticmethod
    def _bytesToDict(data):
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def _dictToBytes(data):
        # The custom json_dumps() will also serialize MappingProxyType objects
        return json_dumps(data).encode("utf-8")

    def _getParamsPath(self, root):
        return '/'.join([root, 'params'])

    def clearBuildParams(self, build_request):
        """Erase the build parameters from ZK to save space"""
        self.kazoo_client.delete(self._getParamsPath(build_request.path),
                                 recursive=True)

    def getBuildParams(self, build_request):
        """Return the parameters for a build request, if they exist.

        Once a build request is accepted by an executor, the params
        may be erased from ZK; this will return None in that case.

        """
        with sharding.BufferedShardReader(
            self.kazoo_client,
                self._getParamsPath(build_request.path)) as stream:
            data = stream.read()
            if not data:
                return None
            return self._bytesToDict(data)
