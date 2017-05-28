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

from tests.base import ZuulTestCase
import zuul.executor.server
import zuul.model


class TestAnsibleJob(ZuulTestCase):
    tenant_config_file = 'config/ansible/main.yaml'

    def setUp(self):
        super(TestAnsibleJob, self).setUp()
        self.test_job = zuul.executor.server.AnsibleJob(self.executor_server,
                                                        zuul.model.Job('test'))

    def test_getHostList_host_keys(self):
        # Test without ssh_port set
        node = {'name': 'fake-host',
                'host_keys': ['fake-host-key'],
                'interface_ip': 'localhost'}
        keys = self.test_job.getHostList({'nodes': [node]})[0]['host_keys']
        self.assertEqual(keys[0], 'localhost fake-host-key')

        # Test with custom ssh_port set
        node['ssh_port'] = 22022
        keys = self.test_job.getHostList({'nodes': [node]})[0]['host_keys']
        self.assertEqual(keys[0], '[localhost]:22022 fake-host-key')
