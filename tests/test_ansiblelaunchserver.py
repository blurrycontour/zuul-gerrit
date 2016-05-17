# Copyright 2016 Rackspace Australia
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

from tests.base import (
    BaseTestCase,
    ZuulAnsibleLauncherTestCase,
)


class TestAnsibleLaunchServer(BaseTestCase):

    def test_console_log_is_captured(self):
        pass

    def test_scp_publisher(self):
        pass

    def test_ftp_publisher(self):
        pass

    def test_timeout_wrapper(self):
        pass

    def test_unknown_jjb_functions(self):
        pass

    def test_prepare_ansible_files(self):
        pass


class TestAnsibleLaunchServerScenario(ZuulAnsibleLauncherTestCase):
    def test_jjb_functions_list(self):
        "Check the jobs were loaded from jjb"
        self.assertEqual(1, len(self.ansible_launcher.jobs))
        self.assertEqual(['hello-world'], self.ansible_launcher.jobs.keys())

    def test_node_assign(self):
        "Check localhost was assigned as a node to this ansible_launcher"
        self.assertEqual(1, len(self.ansible_launcher.node_workers))
        self.assertEqual(['node-local'],
                         self.ansible_launcher.node_workers.keys())

    def test_build_functions_and_worker_register_with_scheduler(self):
        "Check the job has registered and that there is 1 worker available"
        self.assertIn('build:hello-world', self.gearman_server.functions)
        self.assertEqual(
            [0, 0, 1],
            self.gearman_server._getFunctionStats()['build:hello-world'])

    def test_basic_job_runs(self):
        return
        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-ansible-launcher.yaml')
        self.sched.reconfigure(self.config)

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('CRVW', 2)
        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))

        # todo...
        # Wait for job to finish
        # Check results
