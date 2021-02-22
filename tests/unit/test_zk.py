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

import json
import queue
import uuid

import testtools

from zuul import model
from zuul.model import BuildRequest, HoldRequest, MergeRequest
from zuul.zk import ZooKeeperClient
from zuul.zk.change_cache import AbstractChangeCache, ConcurrentUpdateError
from zuul.zk.config_cache import SystemConfigCache, UnparsedConfigCache
from zuul.zk.exceptions import LockException
from zuul.zk.executor import ExecutorApi
from zuul.zk.job_request_queue import JobRequestEvent
from zuul.zk.merger import MergerApi
from zuul.zk.layout import LayoutStateStore, LayoutState
from zuul.zk.locks import locked
from zuul.zk.nodepool import ZooKeeperNodepool
from zuul.zk.sharding import (
    RawShardIO,
    BufferedShardReader,
    BufferedShardWriter,
    NODE_BYTE_SIZE_LIMIT,
)
from zuul.zk.components import (
    BaseComponent, ComponentRegistry, ExecutorComponent
)
from tests.base import (
    BaseTestCase, HoldableExecutorApi, HoldableMergerApi,
    iterate_timeout
)


class ZooKeeperBaseTestCase(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()


class TestZookeeperClient(ZooKeeperBaseTestCase):

    def test_ltime(self):
        ltime = self.zk_client.getCurrentLtime()
        self.assertGreaterEqual(ltime, 0)
        self.assertIsInstance(ltime, int)
        self.assertGreater(self.zk_client.getCurrentLtime(), ltime)


class TestNodepool(ZooKeeperBaseTestCase):

    def setUp(self):
        super().setUp()
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)

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


class TestSharding(ZooKeeperBaseTestCase):

    def test_reader(self):
        shard_io = RawShardIO(self.zk_client.client, "/test/shards")
        self.assertEqual(len(shard_io._shards), 0)

        with BufferedShardReader(
            self.zk_client.client, "/test/shards"
        ) as shard_reader:
            self.assertEqual(shard_reader.read(), b"")
            shard_io.write(b"foobar")
            self.assertEqual(len(shard_io._shards), 1)
            self.assertEqual(shard_io.read(), b"foobar")

    def test_writer(self):
        shard_io = RawShardIO(self.zk_client.client, "/test/shards")
        self.assertEqual(len(shard_io._shards), 0)

        with BufferedShardWriter(
            self.zk_client.client, "/test/shards"
        ) as shard_writer:
            shard_writer.write(b"foobar")

        self.assertEqual(len(shard_io._shards), 1)
        self.assertEqual(shard_io.read(), b"foobar")

    def test_truncate(self):
        shard_io = RawShardIO(self.zk_client.client, "/test/shards")
        shard_io.write(b"foobar")
        self.assertEqual(len(shard_io._shards), 1)

        with BufferedShardWriter(
            self.zk_client.client, "/test/shards"
        ) as shard_writer:
            shard_writer.truncate(0)

        self.assertEqual(len(shard_io._shards), 0)

    def test_shard_bytes_limit(self):
        with BufferedShardWriter(
            self.zk_client.client, "/test/shards"
        ) as shard_writer:
            shard_writer.write(b"x" * (NODE_BYTE_SIZE_LIMIT + 1))
            shard_writer.flush()
            self.assertEqual(len(shard_writer.raw._shards), 2)

    def test_json(self):
        data = {"key": "value"}
        with BufferedShardWriter(
            self.zk_client.client, "/test/shards"
        ) as shard_io:
            shard_io.write(json.dumps(data).encode("utf8"))

        with BufferedShardReader(
            self.zk_client.client, "/test/shards"
        ) as shard_io:
            self.assertDictEqual(json.load(shard_io), data)


class TestUnparsedConfigCache(ZooKeeperBaseTestCase):

    def setUp(self):
        super().setUp()
        self.config_cache = UnparsedConfigCache(self.zk_client)

    def test_files_cache(self):
        master_files = self.config_cache.getFilesCache("project", "master")

        with self.config_cache.readLock("project"):
            self.assertEqual(len(master_files), 0)

        with self.config_cache.writeLock("project"):
            master_files["/path/to/file"] = "content"

        with self.config_cache.readLock("project"):
            self.assertEqual(master_files["/path/to/file"], "content")
            self.assertEqual(len(master_files), 1)

        with self.config_cache.writeLock("project"):
            master_files.clear()
            self.assertEqual(len(master_files), 0)

    def test_valid_for(self):
        tpc = model.TenantProjectConfig("project")
        tpc.extra_config_files = {"foo.yaml", "bar.yaml"}
        tpc.extra_config_dirs = {"foo.d/", "bar.d/"}

        master_files = self.config_cache.getFilesCache("project", "master")
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=-1))

        master_files.setValidFor(tpc.extra_config_files, tpc.extra_config_dirs,
                                 ltime=1)
        self.assertTrue(master_files.isValidFor(tpc, min_ltime=-1))

        tpc.extra_config_files = set()
        tpc.extra_config_dirs = set()
        self.assertTrue(master_files.isValidFor(tpc, min_ltime=-1))
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=2))

        tpc.extra_config_files = {"bar.yaml"}
        tpc.extra_config_dirs = {"bar.d/"}
        # Valid for subset
        self.assertTrue(master_files.isValidFor(tpc, min_ltime=-1))

        tpc.extra_config_files = {"foo.yaml", "bar.yaml"}
        tpc.extra_config_dirs = {"foo.d/", "bar.d/", "other.d/"}
        # Invalid for additional dirs
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=-1))
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=2))

        tpc.extra_config_files = {"foo.yaml", "bar.yaml", "other.yaml"}
        tpc.extra_config_dirs = {"foo.d/", "bar.d/"}
        # Invalid for additional files
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=-1))
        self.assertFalse(master_files.isValidFor(tpc, min_ltime=2))

    def test_cache_ltime(self):
        cache = self.config_cache.getFilesCache("project", "master")
        self.assertEqual(cache.ltime, -1)
        cache.setValidFor(set(), set(), ltime=1)
        self.assertEqual(cache.ltime, 1)

    def test_branch_cleanup(self):
        master_files = self.config_cache.getFilesCache("project", "master")
        release_files = self.config_cache.getFilesCache("project", "release")

        master_files["/path/to/file"] = "content"
        release_files["/path/to/file"] = "content"

        self.config_cache.clearCache("project", "master")
        self.assertEqual(len(master_files), 0)
        self.assertEqual(len(release_files), 1)

    def test_project_cleanup(self):
        master_files = self.config_cache.getFilesCache("project", "master")
        stable_files = self.config_cache.getFilesCache("project", "stable")
        other_files = self.config_cache.getFilesCache("other", "master")

        self.assertEqual(len(master_files), 0)
        self.assertEqual(len(stable_files), 0)
        master_files["/path/to/file"] = "content"
        stable_files["/path/to/file"] = "content"
        other_files["/path/to/file"] = "content"
        self.assertEqual(len(master_files), 1)
        self.assertEqual(len(stable_files), 1)
        self.assertEqual(len(other_files), 1)

        self.config_cache.clearCache("project")
        self.assertEqual(len(master_files), 0)
        self.assertEqual(len(stable_files), 0)
        self.assertEqual(len(other_files), 1)


class TestComponentRegistry(ZooKeeperBaseTestCase):
    def setUp(self):
        super().setUp()
        self.second_zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca,
        )
        self.addCleanup(self.second_zk_client.disconnect)
        self.second_zk_client.connect()
        self.component_registry = ComponentRegistry(self.second_zk_client)

    def assertComponentAttr(self, component_name, attr_name,
                            attr_value, timeout=10):
        for _ in iterate_timeout(
            timeout,
            f"{component_name} in cache has {attr_name} set to {attr_value}",
        ):
            components = list(self.component_registry.all(component_name))
            if (
                len(components) > 0 and
                getattr(components[0], attr_name) == attr_value
            ):
                break

    def assertComponentState(self, component_name, state, timeout=10):
        return self.assertComponentAttr(
            component_name, "state", state, timeout
        )

    def assertComponentStopped(self, component_name, timeout=10):
        for _ in iterate_timeout(
            timeout, f"{component_name} in cache is stopped"
        ):
            components = list(self.component_registry.all(component_name))
            if len(components) == 0:
                break

    def test_component_registry(self):
        self.component_info = ExecutorComponent(self.zk_client, 'test')
        self.component_info.register()
        self.assertComponentState("executor", BaseComponent.STOPPED)

        self.zk_client.client.stop()
        self.assertComponentStopped("executor")

        self.zk_client.client.start()
        self.assertComponentState("executor", BaseComponent.STOPPED)

        self.component_info.state = self.component_info.RUNNING
        self.assertComponentState("executor", BaseComponent.RUNNING)

        self.log.debug("DISCONNECT")
        self.second_zk_client.client.stop()
        self.second_zk_client.client.start()
        self.log.debug("RECONNECT")
        self.component_info.state = self.component_info.PAUSED
        self.assertComponentState("executor", BaseComponent.PAUSED)

        # Make sure the registry didn't create any read/write
        # component objects that re-registered themselves.
        components = list(self.component_registry.all('executor'))
        self.assertEqual(len(components), 1)

        self.component_info.state = self.component_info.RUNNING
        self.assertComponentState("executor", BaseComponent.RUNNING)


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
        request = BuildRequest("A", None, "tenant", "pipeline", '1')
        client.submit(request, {'job': 'test'})
        request_queue.get(timeout=30)

        # Executor receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')
        params = client.getParams(a)
        self.assertEqual(params, {'job': 'test'})
        client.clearParams(a)
        params = client.getParams(a)
        self.assertIsNone(params)

        # Executor locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = BuildRequest.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, BuildRequest.RUNNING)

        # Executor should see no pending requests
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)

        # Executor pauses build
        a.state = BuildRequest.PAUSED
        server.update(a)
        self.assertEqual(client.get(a.path).state, BuildRequest.PAUSED)

        # Scheduler resumes build
        self.assertTrue(event_queue.empty())
        sched_a = client.get(a.path)
        client.requestResume(sched_a)
        (build_request, event) = event_queue.get(timeout=30)
        self.assertEqual(build_request, a)
        self.assertEqual(event, JobRequestEvent.RESUMED)

        # Executor resumes build
        a.state = BuildRequest.RUNNING
        server.update(a)
        server.fulfillResume(a)
        self.assertEqual(client.get(a.path).state, BuildRequest.RUNNING)

        # Scheduler cancels build
        self.assertTrue(event_queue.empty())
        sched_a = client.get(a.path)
        client.requestCancel(sched_a)
        (build_request, event) = event_queue.get(timeout=30)
        self.assertEqual(build_request, a)
        self.assertEqual(event, JobRequestEvent.CANCELED)

        # Executor aborts build
        a.state = BuildRequest.COMPLETED
        server.update(a)
        server.fulfillCancel(a)
        server.unlock(a)
        self.assertEqual(client.get(a.path).state, BuildRequest.COMPLETED)
        for _ in iterate_timeout(5, "Wait for watches to be registered"):
            if self.getZKWatches():
                break

        # Scheduler removes build request on completion
        client.remove(sched_a)

        self.assertEqual(set(self.getZKPaths('/zuul/executor')),
                         set(['/zuul/executor/unzoned',
                              '/zuul/executor/unzoned/locks',
                              '/zuul/executor/unzoned/params',
                              '/zuul/executor/unzoned/requests',
                              '/zuul/executor/unzoned/result-data',
                              '/zuul/executor/unzoned/results',
                              '/zuul/executor/unzoned/waiters']))
        self.assertEqual(self.getZKWatches(), {})

    def test_build_request_remove(self):
        # Test the scheduler forcibly removing a request (perhaps the
        # tenant is being deleted, so there will be no result queue).
        request_queue = queue.Queue()
        event_queue = queue.Queue()

        def rq_put():
            request_queue.put(None)

        def eq_put(br, e):
            event_queue.put((br, e))

        # Simulate the client side
        client = ExecutorApi(self.zk_client)
        # Simulate the server side
        server = ExecutorApi(self.zk_client,
                             build_request_callback=rq_put,
                             build_event_callback=eq_put)

        # Scheduler submits request
        request = BuildRequest("A", None, "tenant", "pipeline", '1')
        client.submit(request, {})
        request_queue.get(timeout=30)

        # Executor receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        # Executor locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = BuildRequest.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, BuildRequest.RUNNING)

        # Executor should see no pending requests
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)
        self.assertTrue(event_queue.empty())

        # Scheduler rudely removes build request
        sched_a = client.get(a.path)
        client.remove(sched_a)

        # Make sure it shows up as deleted
        (build_request, event) = event_queue.get(timeout=30)
        self.assertEqual(build_request, a)
        self.assertEqual(event, JobRequestEvent.DELETED)

        # Executor should not write anything else since the request
        # was deleted.

    def test_build_request_hold(self):
        # Test that we can hold a build request in "queue"
        request_queue = queue.Queue()
        event_queue = queue.Queue()

        def rq_put():
            request_queue.put(None)

        def eq_put(br, e):
            event_queue.put((br, e))

        # Simulate the client side
        client = HoldableExecutorApi(self.zk_client)
        client.hold_in_queue = True
        # Simulate the server side
        server = ExecutorApi(self.zk_client,
                             build_request_callback=rq_put,
                             build_event_callback=eq_put)

        # Scheduler submits request
        request = BuildRequest("A", None, "tenant", "pipeline", '1')
        client.submit(request, {})
        request_queue.get(timeout=30)

        # Executor receives nothing
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)

        # Test releases hold
        a = client.get(request.path)
        self.assertEqual(a.uuid, 'A')
        a.state = BuildRequest.REQUESTED
        client.update(a)

        # Executor receives request
        request_queue.get(timeout=30)
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        # The rest is redundant.

    def test_nonexistent_lock(self):
        request_queue = queue.Queue()
        event_queue = queue.Queue()

        def rq_put():
            request_queue.put(None)

        def eq_put(br, e):
            event_queue.put((br, e))

        # Simulate the client side
        client = ExecutorApi(self.zk_client)

        # Scheduler submits request
        request = BuildRequest("A", None, "tenant", "pipeline", '1')
        client.submit(request, {})
        sched_a = client.get(request.path)

        # Simulate the server side
        server = ExecutorApi(self.zk_client,
                             build_request_callback=rq_put,
                             build_event_callback=eq_put)

        exec_a = server.get(request.path)
        client.remove(sched_a)

        # Try to lock a request that was just removed
        self.assertFalse(server.lock(exec_a))

    def test_lost_build_requests(self):
        # Test that lostBuildRequests() returns unlocked running build
        # requests
        executor_api = ExecutorApi(self.zk_client)

        br = BuildRequest("A", "zone", "tenant", "pipeline", '1')
        executor_api.submit(br, {})

        br = BuildRequest("B", None, "tenant", "pipeline", '1')
        executor_api.submit(br, {})
        path_b = br.path

        br = BuildRequest("C", "zone", "tenant", "pipeline", '1')
        executor_api.submit(br, {})
        path_c = br.path

        br = BuildRequest("D", "zone", "tenant", "pipeline", '1')
        executor_api.submit(br, {})
        path_d = br.path

        br = BuildRequest("E", "zone", "tenant", "pipeline", '1')
        executor_api.submit(br, {})
        path_e = br.path

        b = executor_api.get(path_b)
        c = executor_api.get(path_c)
        d = executor_api.get(path_d)
        e = executor_api.get(path_e)

        b.state = BuildRequest.RUNNING
        executor_api.update(b)

        c.state = BuildRequest.RUNNING
        executor_api.lock(c)
        executor_api.update(c)

        d.state = BuildRequest.COMPLETED
        executor_api.update(d)

        e.state = BuildRequest.PAUSED
        executor_api.update(e)

        # Wait until the latest state transition is reflected in the Executor
        # APIs cache. Using a DataWatch for this purpose could lead to race
        # conditions depending on which DataWatch is executed first. The
        # DataWatch might be triggered for the correct event, but the cache
        # might still be outdated as the DataWatch that updates the cache
        # itself wasn't triggered yet.
        b_cache = executor_api.zone_queues[None]._cached_requests
        e_cache = executor_api.zone_queues['zone']._cached_requests
        for _ in iterate_timeout(30, "cache to be up-to-date"):
            if (b_cache[path_b].state == BuildRequest.RUNNING and
                e_cache[path_e].state == BuildRequest.PAUSED):
                break

        # The lost_builds method should only return builds which are running or
        # paused, but not locked by any executor, in this case build b and e.
        lost_build_requests = list(executor_api.lostRequests())

        self.assertEqual(2, len(lost_build_requests))
        self.assertEqual(b.path, lost_build_requests[0].path)

    def test_lost_build_request_params(self):
        # Test cleaning up orphaned request parameters
        executor_api = ExecutorApi(self.zk_client)

        br = BuildRequest("A", "zone", "tenant", "pipeline", '1')
        executor_api.submit(br, {})

        params_root = executor_api.zone_queues['zone'].PARAM_ROOT
        self.assertEqual(len(executor_api._getAllRequestIds()), 1)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 1)

        # Delete the request but not the params
        self.zk_client.client.delete(br.path)
        self.assertEqual(len(executor_api._getAllRequestIds()), 0)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 1)

        # Clean up leaked params
        executor_api.cleanup(0)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 0)

    def test_existing_build_request(self):
        # Test that an executor sees an existing build request when
        # coming online

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
        client.submit(
            BuildRequest("A", None, "tenant", "pipeline", '1'), {})

        # Simulate the server side
        server = ExecutorApi(self.zk_client,
                             build_request_callback=rq_put,
                             build_event_callback=eq_put)

        # Scheduler submits request
        request_queue.get(timeout=30)

        # Executor receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')


class TestMergerApi(ZooKeeperBaseTestCase):
    def _assertEmptyRoots(self, client):
        self.assertEqual(self.getZKPaths(client.REQUEST_ROOT), [])
        self.assertEqual(self.getZKPaths(client.PARAM_ROOT), [])
        self.assertEqual(self.getZKPaths(client.RESULT_ROOT), [])
        self.assertEqual(self.getZKPaths(client.RESULT_DATA_ROOT), [])
        self.assertEqual(self.getZKPaths(client.WAITER_ROOT), [])
        self.assertEqual(self.getZKPaths(client.LOCK_ROOT), [])
        self.assertEqual(self.getZKWatches(), {})

    def test_merge_request(self):
        # Test the lifecycle of a merge request
        request_queue = queue.Queue()

        # A callback closure for the request queue
        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = MergerApi(self.zk_client)
        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)

        # Scheduler submits request
        payload = {'merge': 'test'}
        request = MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        )
        client.submit(request, payload)
        request_queue.get(timeout=30)

        # Merger receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')
        params = client.getParams(a)
        self.assertEqual(params, payload)
        client.clearParams(a)
        params = client.getParams(a)
        self.assertIsNone(params)

        # Merger locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = MergeRequest.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, MergeRequest.RUNNING)

        # Merger should see no pending requests
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)

        # Merger removes and unlocks merge request on completion
        server.remove(a)
        server.unlock(a)

        self._assertEmptyRoots(client)

    def test_merge_request_hold(self):
        # Test that we can hold a merge request in "queue"
        request_queue = queue.Queue()

        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = HoldableMergerApi(self.zk_client)
        client.hold_in_queue = True
        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)

        # Scheduler submits request
        payload = {'merge': 'test'}
        client.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        request_queue.get(timeout=30)

        # Merger receives nothing
        reqs = list(server.next())
        self.assertEqual(len(reqs), 0)

        # Test releases hold
        # We have to get a new merge_request object to update it.
        a = client.get(f"{client.REQUEST_ROOT}/A")
        self.assertEqual(a.uuid, 'A')
        a.state = MergeRequest.REQUESTED
        client.update(a)

        # Merger receives request
        request_queue.get(timeout=30)
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        server.remove(a)
        # The rest is redundant.
        self._assertEmptyRoots(client)

    def test_merge_request_result(self):
        # Test the lifecycle of a merge request
        request_queue = queue.Queue()

        # A callback closure for the request queue
        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = MergerApi(self.zk_client)
        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)

        # Scheduler submits request
        payload = {'merge': 'test'}
        future = client.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload, needs_result=True)
        request_queue.get(timeout=30)

        # Merger receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        # Merger locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = MergeRequest.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, MergeRequest.RUNNING)

        # Merger reports result
        result_data = {'result': 'ok'}
        server.reportResult(a, result_data)

        self.assertEqual(set(self.getZKPaths(client.RESULT_ROOT)),
                         set(['/zuul/merger/results/A']))
        self.assertEqual(set(self.getZKPaths(client.RESULT_DATA_ROOT)),
                         set(['/zuul/merger/result-data/A',
                              '/zuul/merger/result-data/A/0000000000']))
        self.assertEqual(self.getZKPaths(client.WAITER_ROOT),
                         ['/zuul/merger/waiters/A'])

        # Merger removes and unlocks merge request on completion
        server.remove(a)
        server.unlock(a)

        # Scheduler awaits result
        self.assertTrue(future.wait())
        self.assertEqual(future.data, result_data)

        self._assertEmptyRoots(client)

    def test_lost_merge_request_params(self):
        # Test cleaning up orphaned request parameters
        merger_api = MergerApi(self.zk_client)

        # Scheduler submits request
        payload = {'merge': 'test'}
        merger_api.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        path_a = '/'.join([merger_api.REQUEST_ROOT, 'A'])

        params_root = merger_api.PARAM_ROOT
        self.assertEqual(len(merger_api._getAllRequestIds()), 1)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 1)

        # Delete the request but not the params
        self.zk_client.client.delete(path_a)
        self.assertEqual(len(merger_api._getAllRequestIds()), 0)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 1)

        # Clean up leaked params
        merger_api.cleanup(0)
        self.assertEqual(len(
            self.zk_client.client.get_children(params_root)), 0)

        self._assertEmptyRoots(merger_api)

    def test_lost_merge_request_result(self):
        # Test that we can clean up orphaned merge results
        request_queue = queue.Queue()

        # A callback closure for the request queue
        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = MergerApi(self.zk_client)
        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)

        # Scheduler submits request
        payload = {'merge': 'test'}
        future = client.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload, needs_result=True)

        request_queue.get(timeout=30)

        # Merger receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        # Merger locks request
        self.assertTrue(server.lock(a, blocking=False))
        a.state = MergeRequest.RUNNING
        server.update(a)
        self.assertEqual(client.get(a.path).state, MergeRequest.RUNNING)

        # Merger reports result
        result_data = {'result': 'ok'}
        server.reportResult(a, result_data)

        # Merger removes and unlocks merge request on completion
        server.remove(a)
        server.unlock(a)

        self.assertEqual(set(self.getZKPaths(client.RESULT_ROOT)),
                         set(['/zuul/merger/results/A']))
        self.assertEqual(set(self.getZKPaths(client.RESULT_DATA_ROOT)),
                         set(['/zuul/merger/result-data/A',
                              '/zuul/merger/result-data/A/0000000000']))
        self.assertEqual(self.getZKPaths(client.WAITER_ROOT),
                         ['/zuul/merger/waiters/A'])

        # Scheduler "disconnects"
        self.zk_client.client.delete(future._waiter_path)

        # Find orphaned results
        client.cleanup(age=0)

        self._assertEmptyRoots(client)

    def test_nonexistent_lock(self):
        request_queue = queue.Queue()

        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = MergerApi(self.zk_client)

        # Scheduler submits request
        payload = {'merge': 'test'}
        client.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        client_a = client.get(f"{client.REQUEST_ROOT}/A")

        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)
        server_a = list(server.next())[0]

        client.remove(client_a)

        # Try to lock a request that was just removed
        self.assertFalse(server.lock(server_a))
        self._assertEmptyRoots(client)

    def test_leaked_lock(self):
        client = MergerApi(self.zk_client)

        # Manually create a lock with no underlying request
        self.zk_client.client.create(f"{client.LOCK_ROOT}/A", b'')

        client.cleanup(0)
        self._assertEmptyRoots(client)

    def test_lost_merge_requests(self):
        # Test that lostMergeRequests() returns unlocked running merge
        # requests
        merger_api = MergerApi(self.zk_client)

        payload = {'merge': 'test'}
        merger_api.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        merger_api.submit(MergeRequest(
            uuid='B',
            job_type=MergeRequest.MERGE,
            build_set_uuid='BB',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        merger_api.submit(MergeRequest(
            uuid='C',
            job_type=MergeRequest.MERGE,
            build_set_uuid='CC',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)
        merger_api.submit(MergeRequest(
            uuid='D',
            job_type=MergeRequest.MERGE,
            build_set_uuid='DD',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)

        b = merger_api.get(f"{merger_api.REQUEST_ROOT}/B")
        c = merger_api.get(f"{merger_api.REQUEST_ROOT}/C")
        d = merger_api.get(f"{merger_api.REQUEST_ROOT}/D")

        b.state = MergeRequest.RUNNING
        merger_api.update(b)

        c.state = MergeRequest.RUNNING
        merger_api.lock(c)
        merger_api.update(c)

        d.state = MergeRequest.COMPLETED
        merger_api.update(d)

        # Wait until the latest state transition is reflected in the Merger
        # APIs cache. Using a DataWatch for this purpose could lead to race
        # conditions depending on which DataWatch is executed first. The
        # DataWatch might be triggered for the correct event, but the cache
        # might still be outdated as the DataWatch that updates the cache
        # itself wasn't triggered yet.
        cache = merger_api._cached_requests
        for _ in iterate_timeout(30, "cache to be up-to-date"):
            if (cache[b.path].state == MergeRequest.RUNNING and
                cache[c.path].state == MergeRequest.RUNNING):
                break

        # The lost_merges method should only return merges which are running
        # but not locked by any merger, in this case merge b
        lost_merge_requests = list(merger_api.lostRequests())

        self.assertEqual(1, len(lost_merge_requests))
        self.assertEqual(b.path, lost_merge_requests[0].path)

        # This test does not clean them up, so we can't assert empty roots

    def test_existing_merge_request(self):
        # Test that a merger sees an existing merge request when
        # coming online

        # Test the lifecycle of a merge request
        request_queue = queue.Queue()

        # A callback closure for the request queue
        def rq_put():
            request_queue.put(None)

        # Simulate the client side
        client = MergerApi(self.zk_client)
        payload = {'merge': 'test'}
        client.submit(MergeRequest(
            uuid='A',
            job_type=MergeRequest.MERGE,
            build_set_uuid='AA',
            tenant_name='tenant',
            pipeline_name='check',
            event_id='1',
        ), payload)

        # Simulate the server side
        server = MergerApi(self.zk_client,
                           merge_request_callback=rq_put)

        # Scheduler submits request
        request_queue.get(timeout=30)

        # Merger receives request
        reqs = list(server.next())
        self.assertEqual(len(reqs), 1)
        a = reqs[0]
        self.assertEqual(a.uuid, 'A')

        client.remove(a)
        self._assertEmptyRoots(client)


class TestLocks(ZooKeeperBaseTestCase):

    def test_locking_ctx(self):
        lock = self.zk_client.client.Lock("/lock")
        with locked(lock) as ctx_lock:
            self.assertIs(lock, ctx_lock)
            self.assertTrue(lock.is_acquired)
        self.assertFalse(lock.is_acquired)

    def test_already_locked_ctx(self):
        lock = self.zk_client.client.Lock("/lock")
        other_lock = self.zk_client.client.Lock("/lock")
        other_lock.acquire()
        with testtools.ExpectedException(
            LockException, "Failed to acquire lock .*"
        ):
            with locked(lock, blocking=False):
                pass
        self.assertFalse(lock.is_acquired)

    def test_unlock_exception(self):
        lock = self.zk_client.client.Lock("/lock")
        with testtools.ExpectedException(RuntimeError):
            with locked(lock):
                self.assertTrue(lock.is_acquired)
                raise RuntimeError
        self.assertFalse(lock.is_acquired)


class TestLayoutStore(ZooKeeperBaseTestCase):

    def test_layout_state(self):
        store = LayoutStateStore(self.zk_client, lambda: None)
        state = LayoutState("tenant", "hostname", 0)
        store["tenant"] = state
        self.assertEqual(state, store["tenant"])
        self.assertNotEqual(state.ltime, -1)
        self.assertNotEqual(store["tenant"].ltime, -1)

    def test_ordering(self):
        state_one = LayoutState("tenant", "hostname", 1, ltime=1)
        state_two = LayoutState("tenant", "hostname", 2, ltime=2)

        self.assertGreater(state_two, state_one)


class TestSystemConfigCache(ZooKeeperBaseTestCase):

    def setUp(self):
        super().setUp()
        self.config_cache = SystemConfigCache(self.zk_client, lambda: None)

    def test_set_get(self):
        uac = model.UnparsedAbideConfig()
        uac.tenants = {"foo": "bar"}
        uac.admin_rules = ["bar", "foo"]
        attrs = model.SystemAttributes.fromDict({
            "use_relative_priority": True,
            "max_hold_expiration": 7200,
            "default_hold_expiration": 3600,
            "default_ansible_version": "2.9",
            "web_root": "/web/root",
            "web_status_url": "/web/status",
            "websocket_url": "/web/socket",
        })
        self.config_cache.set(uac, attrs)

        uac_cached, cached_attrs = self.config_cache.get()
        self.assertEqual(uac.uuid, uac_cached.uuid)
        self.assertEqual(uac.tenants, uac_cached.tenants)
        self.assertEqual(uac.admin_rules, uac_cached.admin_rules)
        self.assertEqual(attrs, cached_attrs)

    def test_cache_empty(self):
        with testtools.ExpectedException(RuntimeError):
            self.config_cache.get()

    def test_ltime(self):
        uac = model.UnparsedAbideConfig()
        attrs = model.SystemAttributes()

        self.assertEqual(self.config_cache.ltime, -1)

        self.config_cache.set(uac, attrs)
        self.assertGreater(self.config_cache.ltime, -1)
        self.assertEqual(uac.ltime, self.config_cache.ltime)

        old_ltime = self.config_cache.ltime
        self.config_cache.set(uac, attrs)
        self.assertGreater(self.config_cache.ltime, old_ltime)
        self.assertEqual(uac.ltime, self.config_cache.ltime)

        cache_uac, _ = self.config_cache.get()
        self.assertEqual(uac.ltime, cache_uac.ltime)

    def test_valid(self):
        uac = model.UnparsedAbideConfig()
        attrs = model.SystemAttributes()

        self.assertFalse(self.config_cache.is_valid)

        self.config_cache.set(uac, attrs)
        self.assertTrue(self.config_cache.is_valid)


class DummyChange:

    def __init__(self, project, data=None):
        self.uid = uuid.uuid4().hex
        self.project = project
        self.cache_stat = None
        if data is not None:
            self.deserialize(data)

    @property
    def cache_version(self):
        return -1 if self.cache_stat is None else self.cache_stat.version

    def serialize(self):
        return self.__dict__

    def deserialize(self, data):
        self.__dict__.update(data)


class DummyChangeCache(AbstractChangeCache):

    CHANGE_TYPE_MAP = {
        "DummyChange": DummyChange,
    }

    def _getChangeClass(self, change_type):
        return self.CHANGE_TYPE_MAP[change_type]

    def _getChangeType(self, change):
        return type(change).__name__


class DummySource:

    def getProject(self, project_name):
        return project_name


class DummyConnection:

    def __init__(self):
        self.connection_name = "DummyConnection"
        self.source = DummySource()


class TestChangeCache(ZooKeeperBaseTestCase):

    def setUp(self):
        super().setUp()
        self.cache = DummyChangeCache(self.zk_client, DummyConnection())

    def test_insert(self):
        change_foo = DummyChange("project", {"foo": "bar"})
        change_bar = DummyChange("project", {"bar": "foo"})
        self.cache.set("foo", change_foo)
        self.cache.set("bar", change_bar)

        self.assertEqual(self.cache.get("foo"), change_foo)
        self.assertEqual(self.cache.get("bar"), change_bar)

    def test_update(self):
        change = DummyChange("project", {"foo": "bar"})
        self.cache.set("foo", change)

        change.number = 123
        self.cache.set("foo", change)

        # The change instance must stay the same
        updated_change = self.cache.get("foo")
        self.assertIs(change, updated_change)
        self.assertEqual(change.number, 123)

    def test_delete(self):
        change = DummyChange("project", {"foo": "bar"})
        self.cache.set("foo", change)
        self.cache.delete("foo")
        self.assertIsNone(self.cache.get("foo"))

        # Deleting an non-existent key should not raise an exception
        self.cache.delete("invalid")

    def test_concurrent_update(self):
        change = DummyChange("project", {"foo": "bar"})
        self.cache.set("foo", change)

        updated_change = DummyChange("project", {"foo": "bar"})
        # Copy cache stat over as if this change was retrieved via a
        # different change cache.
        updated_change.cache_stat = change.cache_stat
        self.cache.set("foo", updated_change)
        self.assertIs(self.cache.get("foo"), updated_change)

        # Attempt to update with the old change stat
        with testtools.ExpectedException(ConcurrentUpdateError):
            self.cache.set("foo", change)

    def test_cache_sync(self):
        other_cache = DummyChangeCache(self.zk_client, DummyConnection())

        change = DummyChange("project", {"foo": "bar"})
        self.cache.set("foo", change)

        self.assertIsNotNone(other_cache.get("foo"))

        change_other = other_cache.get("foo")
        change_other.number = 123
        other_cache.set("foo", change_other)

        change = self.cache.get("foo")
        self.assertEqual(change.number, 123)

        other_cache.delete("foo")
        self.assertIsNone(self.cache.get("foo"))

    def test_cleanup(self):
        change = DummyChange("project", {"foo": "bar"})
        self.cache.set("foo", change)

        self.cache.cleanup()
        self.assertEqual(len(self.cache._data_cleanup_candidates), 0)
        self.assertEqual(
            len(self.zk_client.client.get_children(self.cache.data_root)), 1)

        change.number = 123
        self.cache.set("foo", change)

        self.cache.cleanup()
        self.assertEqual(len(self.cache._data_cleanup_candidates), 1)
        self.assertEqual(
            len(self.zk_client.client.get_children(self.cache.data_root)), 2)

        self.cache.cleanup()
        self.assertEqual(len(self.cache._data_cleanup_candidates), 0)
        self.assertEqual(
            len(self.zk_client.client.get_children(self.cache.data_root)), 1)
