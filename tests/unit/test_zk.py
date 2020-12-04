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
from contextlib import suppress

import testtools

from tests.base import BaseTestCase, ChrootedKazooFixture, iterate_timeout
from tests.zk import TestZooKeeperClient

from zuul import model
from zuul.zk.builds import BuildQueue, BuildState
from zuul.zk.config_cache import (
    create_unparsed_files_cache, UnparsedFilesCache
)
from zuul.zk.exceptions import LockException
from zuul.zk.locks import locked, LockFailedError
from zuul.zk.nodepool import ZooKeeperNodepool
from zuul.zk.sharding import BufferedShardIO, NODE_BYTE_SIZE_LIMIT


class ZooKeeperBaseTestCase(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.zk_chroot_fixture = self.useFixture(
            ChrootedKazooFixture(self.id()))
        self.zk_config = '%s:%s%s' % (
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

        self.zk_client = TestZooKeeperClient(hosts=self.zk_config)
        self.zk_client.connect()
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)
        self.addCleanup(self.zk_client.disconnect)


class TestZK(ZooKeeperBaseTestCase):

    def _createRequest(self):
        req = model.HoldRequest()
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


class TestBuilds(ZooKeeperBaseTestCase):

    def test_lost_builds(self):
        build_queue = BuildQueue(self.zk_client)

        build_queue.submit("A", "tenant", "pipeline", {}, "zone")
        path_b = build_queue.submit("B", "tenant", "pipeline", {}, "zone")
        path_c = build_queue.submit("C", "tenant", "pipeline", {}, "zone")
        path_d = build_queue.submit("D", "tenant", "pipeline", {}, "zone")

        b = build_queue.get(path_b)
        c = build_queue.get(path_c)
        d = build_queue.get(path_d)

        b.state = BuildState.RUNNING
        build_queue.update(b)

        c.state = BuildState.RUNNING
        build_queue.update(c)
        build_queue.lock(c)

        d.state = BuildState.COMPLETED
        build_queue.update(d)

        # The lost_builds method should only return builds which are running
        # but not locked by any executor (which is build b in our case).
        lost_builds = list(build_queue.lost_builds())

        self.assertEqual(1, len(lost_builds))
        self.assertEqual(b.path, lost_builds[0].path)

    def test_tree_cache(self):
        zoned_cached_build_queue = BuildQueue(
            self.zk_client, zone_filter=["test-zone-1"], use_cache=True
        )
        unzoned_cached_build_queue = BuildQueue(self.zk_client, use_cache=True)
        uncached_build_queue = BuildQueue(self.zk_client)

        self.zk_client.client.ensure_path(f"{BuildQueue.ROOT}/test-zone-1")
        self.zk_client.client.ensure_path(f"{BuildQueue.ROOT}/test-zone-2")

        for _ in iterate_timeout(10, "zoned cache updated"):
            if len(zoned_cached_build_queue._zone_tree_caches.values()) == 1:
                break

        for _ in iterate_timeout(10, "unzoned cache updated"):
            if len(unzoned_cached_build_queue._zone_tree_caches.values()) == 2:
                break

        self.assertEqual(
            set(["test-zone-1"]),
            set(zoned_cached_build_queue._zone_tree_caches.keys()),
        )

        self.assertEqual(
            set(["test-zone-1", "test-zone-2"]),
            set(unzoned_cached_build_queue._zone_tree_caches.keys()),
        )

        self.assertEqual(
            0, len(uncached_build_queue._zone_tree_caches.values())
        )


class TestSharding(ZooKeeperBaseTestCase):

    def test_read_write(self):
        with BufferedShardIO(
            self.zk_client.client, "/test/shards"
        ) as shard_io:
            self.assertEqual(shard_io.read(), "")
            self.assertEqual(len(shard_io._raw._shards), 0)
            shard_io.write("foobar")
            self.assertEqual(shard_io.read(), "foobar")
            self.assertEqual(len(shard_io._raw._shards), 1)
            shard_io.truncate()
            self.assertEqual(shard_io.read(), "")
            self.assertEqual(len(shard_io._raw._shards), 0)
            shard_io.write("x" * (NODE_BYTE_SIZE_LIMIT + 1))
            shard_io.flush()
            self.assertEqual(len(shard_io._raw._shards), 2)

    def test_json(self):
        data = {"key": "value"}
        with BufferedShardIO(
            self.zk_client.client, "/test/shards"
        ) as shard_io:
            json.dump(data, shard_io)
            self.assertDictEqual(json.load(shard_io), data)


class TestConfigCache(ZooKeeperBaseTestCase):

    def test_unparsed_files(self):
        files = UnparsedFilesCache(self.zk_client, "/test")
        self.assertEqual(len(files), 0)
        files["/path/to/file"] = "content"
        self.assertEqual(files["/path/to/file"], "content")
        self.assertEqual(len(files), 1)

        other_files = UnparsedFilesCache(self.zk_client, "/test")
        self.assertEqual(len(other_files), 1)
        self.assertEqual(other_files["/path/to/file"], "content")

        other_files["/path/to/other"] = "content"
        self.assertEqual(len(files), 2)

        other_files["/path/to/file"] = "changed"
        self.assertEqual(other_files["/path/to/file"], "changed")
        self.assertEqual(files["/path/to/file"], "changed")

        files.clear()
        self.assertEqual(len(files), 0)
        self.assertEqual(len(other_files), 0)

    def test_unparsed_files_cache(self):
        branch_cache = create_unparsed_files_cache(self.zk_client)
        master_files = branch_cache["tenant1"]["project"]["master"]
        release_files = branch_cache["tenant1"]["project"]["release"]
        other_files = branch_cache["tenant1"]["other"]["master"]
        other_tenant_project = branch_cache["tenant2"]["project"]["master"]

        self.assertEqual(len(master_files), 0)
        master_files["/path/to/file"] = "content"
        self.assertEqual(master_files["/path/to/file"], "content")
        self.assertEqual(len(master_files), 1)

        release_files["/path/to/file"] = "content"
        other_files["/path/to/file"] = "content"
        del branch_cache["tenant1"]["project"]["master"]
        master_files = branch_cache["project"]["master"]
        self.assertEqual(len(master_files), 0)
        self.assertEqual(len(release_files), 1)
        self.assertEqual(len(other_files), 1)

        del branch_cache["tenant1"]["project"]
        self.assertEqual(len(release_files), 0)
        self.assertEqual(len(other_files), 1)

        other_tenant_project["/path/to/file"] = "content"
        del branch_cache["tenant1"]
        self.assertEqual(len(other_files), 0)
        self.assertEqual(len(other_tenant_project), 1)


class TestLocks(ZooKeeperBaseTestCase):

    def test_locked_context_manager(self):
        lock1 = self.zk_client.client.Lock("/lock1")
        lock2 = self.zk_client.client.Lock("/lock2")

        with locked(lock1, lock2, blocking=False):
            pass
        self.assertFalse(lock1.is_acquired)
        self.assertFalse(lock2.is_acquired)

    def test_already_locked(self):
        lock1 = self.zk_client.client.Lock("/lock1")
        lock2 = self.zk_client.client.Lock("/lock2")

        lock2.acquire(blocking=False)
        with suppress(LockFailedError):
            with locked(lock1, lock2, blocking=False):
                raise Exception("This should not happen")
        self.assertFalse(lock1.is_acquired)
