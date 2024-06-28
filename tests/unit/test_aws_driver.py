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

from moto import mock_aws

from tests.base import (
    ZuulTestCase,
    iterate_timeout,
    simple_layout,
)


class TestAwsDriver(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    mock_aws = mock_aws()

    def setUp(self):
        self.mock_aws.start()
        super().setUp()

    def tearDown(self):
        self.mock_aws.stop()
        super().tearDown()

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_aws_config(self):
        aws_conn = self.scheds.first.sched.connections.connections['aws']
        self.assertEqual('fake', aws_conn.access_key_id)
        layout = self.scheds.first.sched.abide.tenants.get('tenant-one').layout
        provider = layout.providers['aws-us-east-1-main']
        endpoint = provider.getEndpoint()
        self.assertTrue(len(endpoint.testListAmis()) > 1)

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_aws_launcher(self):
        for _ in iterate_timeout(
                30, "scheduler and launcher to have the same layout"):
            if (self.scheds.first.sched.local_layout_state.get("tenant-one") ==
                self.launcher.local_layout_state.get("tenant-one")):
                break
        providers = self.launcher.tenant_providers['tenant-one']
        self.assertEqual(1, len(providers))
        provider = providers[0]
        endpoint = provider.getEndpoint()
        self.assertTrue(len(endpoint.testListAmis()) > 1)
