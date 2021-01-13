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


import testtools

from tests.zk import TestZooKeeperConnection
from zuul import model
import zuul.zk.exceptions

from tests.base import BaseTestCase, ChrootedKazooFixture, iterate_timeout
from zuul.zk.builds import BuildQueue, BuildState
from zuul.zk.nodepool import ZooKeeperNodepool


class ZooKeeperBaseTestCase(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.zk_chroot_fixture = self.useFixture(
            ChrootedKazooFixture(self.id()))
        self.zk_config = '%s:%s%s' % (
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

        self.zk_client = TestZooKeeperConnection(hosts=self.zk_config)\
            .connect()
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
            zuul.zk.exceptions.LockException,
            "Timeout trying to acquire lock .*"
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
