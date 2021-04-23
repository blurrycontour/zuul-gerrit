# Copyright 2019 Red Hat, Inc.
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

import queue
import testtools

from zuul.model import BuildRequestState, HoldRequest
from zuul.zk import ZooKeeperClient
from zuul.zk.exceptions import LockException
from zuul.zk.executor import ExecutorApi, BuildRequestEvent
from zuul.zk.nodepool import ZooKeeperNodepool

from tests.base import BaseTestCase, iterate_timeout


class ZooKeeperBaseTestCase(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()


class TestZK(ZooKeeperBaseTestCase):

    def _createRequest(self):
        req = HoldRequest()
        req.count = 1
        req.reason = 'some reason'
        req.expiration = 1
        return req

    def test_hold_requests_api(self):
        # Test no requests returns empty list
        self.assertEqual([], self.zk_nodepool.getHoldRequests())

        # Test get on non-existent request is None
        self.assertIsNone(self.zk_nodepool.getHoldRequest('anything'))

        # Test creating a new request
        req1 = self._createRequest()
        self.zk_nodepool.storeHoldRequest(req1)
        self.assertIsNotNone(req1.id)
        self.assertEqual(1, len(self.zk_nodepool.getHoldRequests()))

        # Test getting the request
        req2 = self.zk_nodepool.getHoldRequest(req1.id)
        self.assertEqual(req1.toDict(), req2.toDict())

        # Test updating the request
        req2.reason = 'a new reason'
        self.zk_nodepool.storeHoldRequest(req2)
        req2 = self.zk_nodepool.getHoldRequest(req2.id)
        self.assertNotEqual(req1.reason, req2.reason)

        # Test lock operations
        self.zk_nodepool.lockHoldRequest(req2, blocking=False)
        with testtools.ExpectedException(
            LockException, "Timeout trying to acquire lock .*"
        ):
            self.zk_nodepool.lockHoldRequest(req2, blocking=True, timeout=2)
        self.zk_nodepool.unlockHoldRequest(req2)
        self.assertIsNone(req2.lock)

        # Test deleting the request
        self.zk_nodepool.deleteHoldRequest(req1)
        self.assertEqual([], self.zk_nodepool.getHoldRequests())


class TestExecutorApi(ZooKeeperBaseTestCase):
    def test_build_request(self):
        # Test the lifecycle of a build request
        request_queue = queue.Queue()
        event_queue = queue.Queue()

        # A callback closure for the request queue
        def rq_put():
            request_queue.put(None)

        # and the event queue
        def eq_put(br, e):
            event_queue.put((br, e))

        # Simulate the client side
        client = ExecutorApi(self.zk_client)
        # Simulate the server side
        server = ExecutorApi(self.zk_client,
                             build_request_callback=rq_put,
                             build_event_callback=eq_put)

        # Scheduler submits request
        client.submit("A", "tenant", "pipeline", {}, None)
        request_queue.get(timeout=30)

        # Executor receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        # Executor locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = BuildRequestState.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, BuildRequestState.RUNNING)

        # Executor should see no pending requests
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)

        # Executor pauses build
        a.state = BuildRequestState.PAUSED
        server.update(a)
        self.assertEqual(client.get(a.path).state, BuildRequestState.PAUSED)

        # Scheduler resumes build
        self.assertTrue(event_queue.empty())
        sched_a = client.get(a.path)
        client.requestResume(sched_a)
        (build_request, event) = event_queue.get(timeout=30)
        self.assertEqual(build_request, a)
        self.assertEqual(event, BuildRequestEvent.RESUMED)

        # Executor resumes build
        a.state = BuildRequestState.RUNNING
        server.update(a)
        server.fulfillResume(a)
        self.assertEqual(client.get(a.path).state, BuildRequestState.RUNNING)

        # Scheduler cancels build
        self.assertTrue(event_queue.empty())
        sched_a = client.get(a.path)
        client.requestCancel(sched_a)
        (build_request, event) = event_queue.get(timeout=30)
        self.assertEqual(build_request, a)
        self.assertEqual(event, BuildRequestEvent.CANCELED)

        # Executor aborts build
        a.state = BuildRequestState.COMPLETED
        server.update(a)
        server.fulfillCancel(a)
        server.unlock(a)
        self.assertEqual(client.get(a.path).state, BuildRequestState.COMPLETED)

        # Scheduler removes build request on completion
        client.remove(sched_a)

    # TODO: test scheduler forcibly removing buildrequest
    # TODO: test hold process

    def test_lost_build_requests(self):
        # Test that lostBuildRequests() returns unlocked running build
        # requests
        executor_api = ExecutorApi(self.zk_client, zone_filter=['zone'])

        executor_api.submit("A", "tenant", "pipeline", {}, "zone")
        path_b = executor_api.submit("B", "tenant", "pipeline", {}, "zone")
        path_c = executor_api.submit("C", "tenant", "pipeline", {}, "zone")
        path_d = executor_api.submit("D", "tenant", "pipeline", {}, "zone")
        path_e = executor_api.submit("E", "tenant", "pipeline", {}, "zone")

        b = executor_api.get(path_b)
        c = executor_api.get(path_c)
        d = executor_api.get(path_d)
        e = executor_api.get(path_e)

        b.state = BuildRequestState.RUNNING
        executor_api.update(b)

        c.state = BuildRequestState.RUNNING
        executor_api.lock(c)
        executor_api.update(c)

        d.state = BuildRequestState.COMPLETED
        executor_api.update(d)

        e.state = BuildRequestState.PAUSED
        executor_api.update(e)

        # Wait until the latest state transition is reflected in the Executor
        # APIs cache. Using a DataWatch for this purpose could lead to race
        # conditions depending on which DataWatch is executed first. The
        # DataWatch might be triggered for the correct event, but the cache
        # might still be outdated as the DataWatch that updates the cache
        # itself wasn't triggered yet.
        for _ in iterate_timeout(30, "wait for cache to be up-to-date"):
            if (
                executor_api._cached_build_requests[path_e].state
                == BuildRequestState.PAUSED
            ):
                break

        # The lost_builds method should only return builds which are running or
        # paused, but not locked by any executor, in this case build b and e.
        lost_build_requests = list(executor_api.lostBuildRequests())

        self.assertEqual(2, len(lost_build_requests))
        self.assertEqual(b.path, lost_build_requests[0].path)
