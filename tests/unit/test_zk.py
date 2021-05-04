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

import testtools

from tests.base import BaseTestCase

from zuul import model
from zuul.zk import ZooKeeperClient
from zuul.zk.exceptions import LockException
from zuul.zk.nodepool import ZooKeeperNodepool
from zuul.zk.sharding import (
    RawShardIO,
    BufferedShardReader,
    BufferedShardWriter,
    NODE_BYTE_SIZE_LIMIT,
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
        self.assertIsInstance(self.zk_client.ltime, int)
        self.assertGreaterEqual(self.zk_client.ltime, -1)


class TestNodepool(ZooKeeperBaseTestCase):

    def setUp(self):
        super().setUp()
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)

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
