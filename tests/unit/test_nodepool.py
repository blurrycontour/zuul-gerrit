# Copyright 2017 Red Hat, Inc.
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

import time

from zuul import model
import zuul.nodepool

from tests.base import BaseTestCase, FakeNodepool
from zuul.zk import ZooKeeperClient
from zuul.zk.nodepool import ZooKeeperNodepool


class NodepoolWithCallback(zuul.nodepool.Nodepool):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provisioned_requests = []

    def _handleNodeRequestEvent(self, request, event, request_id=None):
        super()._handleNodeRequestEvent(request, event, request_id)
        self.provisioned_requests.append(request)


class TestNodepoolBase(BaseTestCase):
    # Tests the Nodepool interface class using a fake nodepool and
    # scheduler.

    def setUp(self):
        super().setUp()

        self.statsd = None
        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()
        self.hostname = 'nodepool-test-hostname'

        # This class implements the scheduler methods zuul.nodepool
        # needs, so we pass 'self' as the scheduler.
        self.nodepool = NodepoolWithCallback(
            self.zk_client, self.hostname, self.statsd, self)

        self.fake_nodepool = FakeNodepool(self.zk_chroot_fixture)
        self.addCleanup(self.fake_nodepool.stop)

    def waitForRequests(self):
        # Wait until all requests are complete.
        # TODO (felix): Would it make sense to provide a data watch here on the
        # node requests to wait for the updates and directly get the data so
        # we can assert the node request state in the tests?
        while self.nodepool.requests:
            time.sleep(0.1)


class TestNodepool(TestNodepoolBase):
    def test_node_request(self):
        # Test a simple node request

        nodeset = model.NodeSet()
        nodeset.addNode(model.Node(['controller', 'foo'], 'ubuntu-xenial'))
        nodeset.addNode(model.Node(['compute'], 'ubuntu-xenial'))
        job = model.Job('testjob')
        job.nodeset = nodeset
        request = self.nodepool.requestNodes(
            "test-uuid", job, "tenant", "pipeline", "provider", 0, 0)
        self.waitForRequests()
        request = self.nodepool.zk_nodepool.getNodeRequest(request.id)
        self.assertEqual(len(self.nodepool.provisioned_requests), 1)
        # We have to look up the request from ZK directly to check the
        # state.
        zk_request = self.zk_nodepool.getNodeRequest(request.id)
        self.assertEqual(zk_request.state, 'fulfilled')

        # Accept the nodes
        new_nodeset = self.nodepool.getNodeSet(request, nodeset)
        self.assertIsNotNone(new_nodeset)
        # acceptNodes will be called on the executor, but only if the
        # noderequest was accepted before.
        executor_nodeset = nodeset.copy()
        self.nodepool.acceptNodes(request, executor_nodeset)

        for node in executor_nodeset.getNodes():
            self.assertIsNotNone(node.lock)
            self.assertEqual(node.state, 'ready')

        # Mark the nodes in use
        self.nodepool.useNodeSet(executor_nodeset)
        for node in executor_nodeset.getNodes():
            self.assertEqual(node.state, 'in-use')

        # Return the nodes
        self.nodepool.returnNodeSet(executor_nodeset)
        for node in executor_nodeset.getNodes():
            self.assertIsNone(node.lock)
            self.assertEqual(node.state, 'used')

    def test_node_request_canceled(self):
        # Test that node requests can be canceled

        nodeset = model.NodeSet()
        nodeset.addNode(model.Node(['controller'], 'ubuntu-xenial'))
        nodeset.addNode(model.Node(['compute'], 'ubuntu-xenial'))
        job = model.Job('testjob')
        job.nodeset = nodeset
        self.fake_nodepool.pause()
        request = self.nodepool.requestNodes(
            "test-uuid", job, "tenant", "pipeline", "provider", 0, 0)
        self.nodepool.cancelRequest(request)

        self.waitForRequests()
        self.assertEqual(len(self.nodepool.provisioned_requests), 0)

    def test_node_request_priority(self):
        # Test that requests are satisfied in priority order

        nodeset = model.NodeSet()
        nodeset.addNode(model.Node(['controller', 'foo'], 'ubuntu-xenial'))
        nodeset.addNode(model.Node(['compute'], 'ubuntu-xenial'))
        job = model.Job('testjob')
        job.nodeset = nodeset
        self.fake_nodepool.pause()
        request1 = self.nodepool.requestNodes(
            "test-uuid", job, "tenant", "pipeline", "provider", 0, 1)
        request2 = self.nodepool.requestNodes(
            "test-uuid", job, "tenant", "pipeline", "provider", 0, 0)
        self.fake_nodepool.unpause()
        self.waitForRequests()
        request1 = self.nodepool.zk_nodepool.getNodeRequest(request1.id)
        request2 = self.nodepool.zk_nodepool.getNodeRequest(request2.id)
        self.assertEqual(len(self.nodepool.provisioned_requests), 2)
        self.assertEqual(request1.state, 'fulfilled')
        self.assertEqual(request2.state, 'fulfilled')
        self.assertTrue(request2.state_time < request1.state_time)
