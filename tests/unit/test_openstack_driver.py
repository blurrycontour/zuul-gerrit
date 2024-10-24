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

from zuul.driver.openstack import OpenstackDriver
import zuul.driver.openstack.openstackendpoint

from tests.fake_openstack import (
    FakeOpenstackCloud,
    FakeOpenstackProviderEndpoint,
)
from tests.base import (
    FIXTURE_DIR,
    ZuulTestCase,
    simple_layout,
    return_data,
)
from tests.unit.test_launcher import ImageMocksFixture
from tests.unit.test_cloud_driver import BaseCloudDriverTest


class BaseOpenstackDriverTest(ZuulTestCase):
    cloud_test_image_format = 'qcow2'
    cloud_test_provider_name = 'openstack-main'
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
        self.patch(zuul.driver.openstack.openstackendpoint,
                   'CACHE_TTL', 1)
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackDriver(BaseOpenstackDriverTest, BaseCloudDriverTest):
    def _assertProviderNodeAttributes(self, pnode):
        super()._assertProviderNodeAttributes(pnode)
        self.assertEqual('fakecloud', pnode.cloud)
        self.assertEqual('region1', pnode.region)

    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_node_lifecycle(self):
        self._test_node_lifecycle('debian-normal')

    @simple_layout('layouts/openstack/nodepool-image.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        BaseOpenstackDriverTest.debian_return_data,
    )
    def test_openstack_diskimage(self):
        self._test_diskimage()


# Openstack-driver specific tests
class TestOpenstackDriverFloatingIp(BaseOpenstackDriverTest,
                                    BaseCloudDriverTest):
    # This test is for nova-net clouds with floating ips that require
    # manual attachment.
    openstack_needs_floating_ip = True
    openstack_auto_attach_floating_ip = False

    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_fip(self):
        self._test_node_lifecycle('debian-normal')


class TestOpenstackDriverAutoAttachFloatingIp(BaseOpenstackDriverTest,
                                              BaseCloudDriverTest):
    openstack_needs_floating_ip = True
    openstack_auto_attach_floating_ip = True

    @simple_layout('layouts/openstack/nodepool.yaml', enable_nodepool=True)
    def test_openstack_auto_attach_fip(self):
        self._test_node_lifecycle('debian-normal')
