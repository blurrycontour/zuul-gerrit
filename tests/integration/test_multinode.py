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

import zuul.zk
import zuul.nodepool
from zuul import model

from tests.base import BaseTestCase, ChrootedKazooFixture, FakeNodepool


class TestMultiNode(BaseTestCase):
    # Tests multinode deploy using static nodes from zuul's fake nodepool.

    def setUp(self):
        super(BaseTestCase, self).setUp()

        self.zk_chroot_fixture = self.useFixture(ChrootedKazooFixture())
        self.zk_config = '%s:%s%s' % (
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

        self.zk = zuul.zk.ZooKeeper()
        self.zk.connect(self.zk_config)
        self.hostname = 'nodepool-test-hostname'

        self.provisioned_requests = []

        self.nodepool = zuul.nodepool.Nodepool(self)

        self.fake_nodepool = FakeNodepool(
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

    def waitForRequests(self):
        # Wait until all requests are complete.
        while self.nodepool.requests:
            time.sleep(0.1)

    def onNodesProvisioned(self, request):
        # This is a scheduler method that the nodepool class calls
        # back when a request is provisioned.
        self.provisioned_requests.append(request)

    def provisionNodes(self):
        # Provision a pair of static nodes
        nodeset = model.NodeSet()
        nodeset.addNode(model.Node('master', 'ubuntu-xenial'))
        nodeset.addNode(model.Node('minion', 'ubuntu-xenial'))
        job = model.Job('testjob')
        job.nodeset = nodeset
        request = self.nodepool.requestNodes(None, job)
        self.waitForRequests()

        # Accept the nodes
        self.nodepool.acceptNodes(request)
        nodeset = request.nodeset

        return nodeset

    def runAnsible(self):
        # Get some nodes and TODO(eggshell): run Ansible playbooks

        nodeset = self.provisionNodes(self)
