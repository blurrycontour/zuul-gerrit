# Copyright 2018 Red Hat, Inc.
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
import textwrap

from tests.base import AnsibleZuulTestCase


class TestActionModules(AnsibleZuulTestCase):
    tenant_config_file = 'config/remote-action-modules/main.yaml'

    def setUp(self):
        super(TestActionModules, self).setUp()
        self.fake_nodepool.remote_ansible = True

    def _run_job(self, job_name, result):
        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        conf = textwrap.dedent(
            """
            - job:
                name: {job_name}
                run: playbooks/{job_name}.yaml
                nodeset:
                  nodes:
                    - name: controller
                      label: whatever

            - project:
                check:
                  jobs:
                    - {job_name}
            """.format(job_name=job_name))

        file_dict = {'zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        job = self.getJobFromHistory(job_name)
        with self.jobLog(job):
            build = self.history[-1]
            self.assertEqual(build.result, result)

    def test_copy_module(self):
        self._run_job('copy-good', 'SUCCESS')
        self._run_job('copy-bad', 'FAILURE')
