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


import zuul.zk
from zuul import model

from tests.base import BaseTestCase, ChrootedKazooFixture


class TestZK(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.zk_chroot_fixture = self.useFixture(
            ChrootedKazooFixture(self.id()))
        self.zk_config = '%s:%s%s' % (
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

        self.zk = zuul.zk.ZooKeeper()
        self.addCleanup(self.zk.disconnect)
        self.zk.connect(self.zk_config)

    def test_getHoldRequests(self):
        self.assertEqual([], self.zk.getHoldRequests())

    def test_getHoldRequest(self):
        # Create a new request
        req = model.HoldRequest()
        self.zk.storeHoldRequest(req)

        # Make sure one is created
        self.assertEqual(1, len(self.zk.getHoldRequests()))

        # Get the same request we just created
        req2 = self.zk.getHoldRequest(req.id)
        self.assertEqual(req.toDict(), req2.toDict())

    def test_storeHoldRequest(self):
        req = model.HoldRequest()
        self.assertIsNone(req.id)
        self.zk.storeHoldRequest(req)
        self.assertIsNotNone(req.id)
