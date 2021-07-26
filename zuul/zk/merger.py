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

from zuul.zk.watchers import ExistingDataWatch

from kazoo.exceptions import LockTimeout, NoNodeError
from kazoo.protocol.states import EventType
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.model import MergeRequest
from zuul.zk import ZooKeeperSimpleBase, sharding
from zuul.zk.event_queues import MergerEventResultFuture
from zuul.zk.exceptions import MergeRequestNotFound


class MergerApi(ZooKeeperSimpleBase):

    MERGE_REQUEST_ROOT = "/zuul/merge-requests"
    MERGE_RESULT_ROOT = "/zuul/merge-results"
    MERGE_WAITER_ROOT = "/zuul/merge-waiters"
    LOCK_ROOT = "/zuul/merge-request-locks"

    log = logging.getLogger("zuul.zk.merger.MergerApi")

    def __init__(self, client, merge_request_callback=None):
        super().__init__(client)

        self.merge_request_callback = merge_request_callback

        # path -> merge request
        self._cached_merge_requests = {}

        self.register()

    @property
    def initial_state(self):
        # This supports holding merge requests in tests
        return MergeRequest.REQUESTED

    def register(self):
        self.kazoo_client.ensure_path(self.MERGE_REQUEST_ROOT)
        self.kazoo_client.ensure_path(self.MERGE_RESULT_ROOT)
        self.kazoo_client.ensure_path(self.MERGE_WAITER_ROOT)

        # Register a child watch that listens for new merge requests
        self.kazoo_client.ChildrenWatch(
            self.MERGE_REQUEST_ROOT,
            self._makeMergeRequestWatcher(self.MERGE_REQUEST_ROOT),
            send_event=True,
        )

    def _makeMergeStateWatcher(self, path):
        def watch(data, stat, event=None):
            return self._watchMergeState(path, data, stat, event)
        return watch

    def _watchMergeState(self, path, data, stat, event=None):
        if not event or event.type == EventType.CHANGED:
            # Don't process change events w/o any data. This can happen when a
            # "slow" change watch tried to retrieve the data of a znode that
            # was deleted in the meantime.
            if not data:
                return
            # As we already get the data and the stat value, we can directly
            # use it without asking ZooKeeper for the data again.
            content = self._bytesToDict(data)
            if not content:
                return

            # We need this one for the HOLD -> REQUESTED check further down
            old_merge_request = self._cached_merge_requests.get(path)

            merge_request = MergeRequest.fromDict(content)
            merge_request.path = path
            merge_request._zstat = stat
            self._cached_merge_requests[path] = merge_request

            # NOTE (felix): This is a test-specific condition: For test cases
            # which are using hold_merge_jobs_in_queue the state change on the
            # merge request from HOLD to REQUESTED is done outside of the
            # merger.
            # Thus, we must also set the wake event (the callback) so the
            # merger can pick up those jobs after they are released. To not
            # cause a thundering herd problem in production for each cache
            # update, the callback is only called under this very specific
            # condition that can only occur in the tests.
            if (
                self.merge_request_callback
                and old_merge_request
                and old_merge_request.state == MergeRequest.HOLD
                and merge_request.state == MergeRequest.REQUESTED
            ):
                self.merge_request_callback()

        elif event.type == EventType.DELETED:
            merge_request = self._cached_merge_requests.get(path)
            with suppress(KeyError):
                del self._cached_merge_requests[path]

            # Return False to stop the datawatch as the build got deleted.
            return False

    def _makeMergeRequestWatcher(self, path):
        def watch(merge_requests, event=None):
            return self._watchMergeRequests(path, merge_requests)
        return watch

    def _watchMergeRequests(self, path, merge_requests):
        # The merge_requests list always contains all active children. Thus, we
        # first have to find the new ones by calculating the delta between the
        # merge_requests list and our current cache entries.
        # NOTE (felix): We could also use this list to determine the deleted
        # merge requests, but it's easier to do this in the DataWatch for the
        # single merge request instead. Otherwise we have to deal with race
        # conditions between the children and the data watch as one watch might
        # update a cache entry while the other tries to remove it.

        merge_request_paths = {
            f"{path}/{uuid}" for uuid in merge_requests
        }

        new_merge_requests = merge_request_paths - set(
            self._cached_merge_requests.keys()
        )

        for req_path in new_merge_requests:
            ExistingDataWatch(self.kazoo_client,
                              req_path,
                              self._makeMergeStateWatcher(req_path))

        # Notify the user about new merge requests if a callback is provided,
        # but only if there are new requests (we don't want to fire on the
        # initial callback from kazoo from registering the datawatch).
        if new_merge_requests and self.merge_request_callback:
            self.merge_request_callback()

    def _iterMergeRequests(self):
        # As the entries in the cache dictionary are added and removed via
        # data and children watches, we can't simply iterate over it in here,
        # as the values might change during iteration.
        for key in list(self._cached_merge_requests.keys()):
            try:
                merge_request = self._cached_merge_requests[key]
            except KeyError:
                continue
            yield merge_request

    def inState(self, *states):
        if not states:
            # If no states are provided, build a tuple containing all available
            # ones to always match. We need a tuple to be compliant to the
            # type of *states above.
            states = MergeRequest.ALL_STATES

        merge_requests = list(
            filter(lambda b: b.state in states, self._iterMergeRequests())
        )

        # Sort the list of merge requests by precedence and their creation time
        # in ZooKeeper in ascending order to prevent older requests from
        # starving.
        return (b for b in sorted(merge_requests))

    def next(self):
        yield from self.inState(MergeRequest.REQUESTED)

    def submit(self, merge_request, params, needs_result=False, event=None):
        log = get_annotated_logger(self.log, event=event)

        path = "/".join([self.MERGE_REQUEST_ROOT, merge_request.uuid])
        merge_request.path = path
        result = None

        # If a result is needed, create the result_path with the same UUID and
        # store it on the merge request, so the merger server can store the
        # result there.
        if needs_result:
            result_path = "/".join(
                [self.MERGE_RESULT_ROOT, merge_request.uuid]
            )
            waiter_path = "/".join(
                [self.MERGE_WAITER_ROOT, merge_request.uuid]
            )
            result = MergerEventResultFuture(self.client, result_path,
                                             waiter_path)
            merge_request.result_path = result_path

        log.debug("Submitting merge request to ZooKeeper %s", merge_request)

        tr = self.kazoo_client.transaction()

        tr.create(waiter_path, b'', ephemeral=True)
        tr.create(
            path,
            self._dictToBytes(merge_request.toDict()),
        )
        params_path = self._getParamsPath(path)
        tr.create(params_path)
        params_path = '/'.join([params_path, 'seq'])
        with sharding.BufferedShardWriter(tr, params_path) as stream:
            stream.write(self._dictToBytes(params))
        self.client.commitTransaction(tr)

        return result

    def update(self, merge_request):
        log = get_annotated_logger(
            self.log, event=None, build=merge_request.uuid
        )
        log.debug("Updating merge request %s", merge_request)

        if merge_request._zstat is None:
            log.debug(
                "Cannot update merge request %s: Missing version information.",
                merge_request.uuid,
            )
            return
        try:
            zstat = self.kazoo_client.set(
                merge_request.path,
                self._dictToBytes(merge_request.toDict()),
                version=merge_request._zstat.version,
            )
            # Update the zstat on the item after updating the ZK node
            merge_request._zstat = zstat
        except NoNodeError:
            raise MergeRequestNotFound(
                f"Could not update {merge_request.path}"
            )

    def reportResult(self, merge_request, result):
        self.kazoo_client.create(
            merge_request.result_path,
            self._dictToBytes(result),
            makepath=True,
        )

    def get(self, path):
        """Get a merge request

        Note: do not mix get with iteration; iteration returns cached
        MergeRequests while get returns a newly created object each time. If
        you lock a MergeRequest, you must use the same object to unlock it.

        """
        try:
            data, zstat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        content = self._bytesToDict(data)

        merge_request = MergeRequest.fromDict(content)
        merge_request.path = path
        merge_request._zstat = zstat

        return merge_request

    def remove(self, merge_request):
        self.log.debug("Removing merge request %s", merge_request)
        try:
            self.kazoo_client.delete(merge_request.path, recursive=True)
        except NoNodeError:
            # Nothing to do if the node is already deleted
            pass

        try:
            # Delete the lock parent node as well
            path = "/".join([self.LOCK_ROOT, merge_request.uuid])
            self.kazoo_client.delete(path, recursive=True)
        except NoNodeError:
            pass

    def lock(self, merge_request, blocking=True, timeout=None):
        path = "/".join([self.LOCK_ROOT, merge_request.uuid])
        have_lock = False
        lock = None
        try:
            lock = Lock(self.kazoo_client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            have_lock = False
            self.log.error(
                "Timeout trying to acquire lock: %s", merge_request.uuid
            )

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            return False

        if not self.kazoo_client.exists(merge_request.path):
            lock.release()
            self.log.error(
                "Merge not found for locking: %s", merge_request.uuid
            )

            # We may have just re-created the lock parent node just after the
            # scheduler deleted it; therefore we should (re-) delete it.
            try:
                # Delete the lock parent node as well.
                path = "/".join([self.LOCK_ROOT, merge_request.uuid])
                self.kazoo_client.delete(path, recursive=True)
            except NoNodeError:
                pass

            return False

        merge_request.lock = lock

        return True

    def unlock(self, merge_request):
        if merge_request.lock is None:
            self.log.warning(
                "MergeRequest %s does not hold a lock", merge_request
            )
        else:
            merge_request.lock.release()
            merge_request.lock = None

    def isLocked(self, merge_request):
        path = "/".join([self.LOCK_ROOT, merge_request.uuid])
        lock = Lock(self.kazoo_client, path)
        is_locked = len(lock.contenders()) > 0
        return is_locked

    # TODO (felix): Move the cleanup to the apscheduler in the zuul scheduler.
    def lostMergeRequests(self):
        # Get a list of merge requests which are running but not locked by any
        # merger.
        yield from filter(
            lambda b: not self.isLocked(b),
            self.inState(MergeRequest.RUNNING),
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

    def clearMergeParams(self, merge_request):
        """Erase the merge parameters from ZK to save space"""
        self.kazoo_client.delete(self._getParamsPath(merge_request.path),
                                 recursive=True)

    def getMergeParams(self, merge_request):
        """Return the parameters for a merge request, if they exist.

        Once a merge request is accepted by an executor, the params
        may be erased from ZK; this will return None in that case.

        """
        with sharding.BufferedShardReader(
            self.kazoo_client,
                self._getParamsPath(merge_request.path)) as stream:
            data = stream.read()
            if not data:
                return None
            return self._bytesToDict(data)
