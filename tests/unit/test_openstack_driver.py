# Copyright 2024 Acme Gating, LLC
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

import os

import fixtures
import testtools
from kazoo.exceptions import NoNodeError

from zuul import model
from zuul.launcher.client import LauncherClient
from zuul.driver.openstack import OpenstackDriver

from tests.fake_openstack import (
    FakeOpenstackCloud,
    FakeOpenstackProviderEndpoint,
)
from tests.base import (
    FIXTURE_DIR,
    ZuulTestCase,
    iterate_timeout,
    simple_layout,
    return_data,
)
from tests.unit.test_launcher import ImageMocksFixture


class BaseOpenstackDriverTest(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    debian_return_data = {
        'zuul': {
            'artifacts': [
                {
                    'name': 'raw image',
                    'url': 'http://example.com/image.raw',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'debian-local',
                        'format': 'qcow2',
                        'sha256': ('59984dd82f51edb3777b969739a92780'
                                   'a520bb314b8d64b294d5de976bd8efb9'),
                        'md5sum': '262278e1632567a907e4604e9edd2e83',
                    }
                },
            ]
        }
    }
    openstack_needs_floating_ip = False
    openstack_auto_attach_floating_ip = True

    def setUp(self):
        self.initTestConfig()
        self.useFixture(ImageMocksFixture())
        clouds_yaml = os.path.join(FIXTURE_DIR, 'clouds.yaml')
        self.useFixture(
            fixtures.EnvironmentVariable('OS_CLIENT_CONFIG_FILE', clouds_yaml))
        self.fake_cloud = FakeOpenstackCloud(
            needs_floating_ip=self.openstack_needs_floating_ip,
            auto_attach_floating_ip=self.openstack_auto_attach_floating_ip,
        )
        self.patch(OpenstackDriver, '_endpoint_class',
                   FakeOpenstackProviderEndpoint)
        self.patch(FakeOpenstackProviderEndpoint,
                   '_fake_cloud', self.fake_cloud)
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def _test_openstack_node_lifecycle(self, label):
        nodeset = model.NodeSet()
        nodeset.addNode(model.Node("node", label))

        ctx = self.createZKContext(None)
        request = self.requestNodes([n.label for n in nodeset.getNodes()])

        client = LauncherClient(self.zk_client, None)
        request = client.getRequest(request.uuid)

        self.assertEqual(request.state, model.NodesetRequest.State.FULFILLED)
        self.assertEqual(len(request.nodes), 1)

        client.acceptNodeset(request, nodeset)
        self.waitUntilSettled()

        with testtools.ExpectedException(NoNodeError):
            # Request should be gone
            request.refresh(ctx)

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertIsNotNone(pnode)
            self.assertTrue(pnode.hasLock())

        client.useNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertTrue(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.IN_USE)

        client.returnNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertFalse(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.USED)

            for _ in iterate_timeout(60, "node to be deleted"):
                try:
                    pnode.refresh(ctx)
                except NoNodeError:
                    break


class TestOpenstackDriver(BaseOpenstackDriverTest):
    # TODO: make this a generic driver test
    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_config(self):
        layout = self.scheds.first.sched.abide.tenants.get('tenant-one').layout
        provider = layout.providers['openstack-main']
        endpoint = provider.getEndpoint()
        self.assertEqual([], list(endpoint.listInstances()))

    # TODO: make this a generic driver test
    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_node_lifecycle(self):
        self._test_openstack_node_lifecycle('debian-normal')

    # TODO: make this a generic driver test
    @simple_layout('layouts/openstack/nodepool-image.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        BaseOpenstackDriverTest.debian_return_data,
    )
    def test_openstack_diskimage(self):
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
        ], ordered=False)

        name = 'review.example.com%2Forg%2Fcommon-config/debian-local'
        artifacts = self.launcher.image_build_registry.\
            getArtifactsForImage(name)
        self.assertEqual(1, len(artifacts))
        self.assertEqual('qcow2', artifacts[0].format)
        self.assertTrue(artifacts[0].validated)
        uploads = self.launcher.image_upload_registry.getUploadsForImage(
            name)
        self.assertEqual(1, len(uploads))
        self.assertEqual(artifacts[0].uuid, uploads[0].artifact_uuid)
        self.assertIsNotNone(uploads[0].external_id)
        self.assertTrue(uploads[0].validated)


# Openstack-driver specific tests
class TestOpenstackDriverFloatingIp(BaseOpenstackDriverTest):
    # This test is for nova-net clouds with floating ips that require
    # manual attachment.
    openstack_needs_floating_ip = True
    openstack_auto_attach_floating_ip = False

    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_fip(self):
        self._test_openstack_node_lifecycle('debian-normal')


class TestOpenstackDriverAutoAttachFloatingIp(BaseOpenstackDriverTest):
    openstack_needs_floating_ip = True
    openstack_auto_attach_floating_ip = True

    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_auto_attach_fip(self):
        self._test_openstack_node_lifecycle('debian-normal')
