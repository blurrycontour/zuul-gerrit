# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2016 Red Hat, Inc.
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


from tests.base import ZuulTestCase


class TestGiteaDriver(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'
    tenant_config_file = 'config/gitea-driver/main.yaml'

    def setUp(self):
        super(TestGiteaDriver, self).setUp()
        self.gitea_connection = self.scheds.first.sched.connections\
            .getSource('gitea').connection

    def setup_config(self, config_file: str):
        config = super(TestGiteaDriver, self).setup_config(config_file)
        config.set('connection gitea', 'baseurl', self.upstream_root)
        return config

    def test_basic(self):
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        # Check that we have the git source for common-config and the
        # gerrit source for the project.
        self.assertEqual('gitea', tenant.config_projects[0].source.name)
        self.assertEqual('common-config', tenant.config_projects[0].name)
        self.assertEqual('giteat', tenant.untrusted_projects[0].source.name)
        self.assertEqual('org/project', tenant.untrusted_projects[0].name)
