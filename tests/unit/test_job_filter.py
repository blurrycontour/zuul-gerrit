# Copyright 2019 Red Hat
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


class TestGerritJobFilter(ZuulTestCase):
    config_file = 'zuul.conf'
    tenant_config_file = 'config/job-filter/main.yaml'

    def test_job_filter(self):
        "Test that jobs are filtered based on comment"
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(A.addApproval(
            'Code-Review', 0, message='recheck-filter test-matrix[12]'))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='test-matrix1', result='SUCCESS', changes="1,1"),
            dict(name='test-matrix2', result='SUCCESS', changes="1,1"),
        ])
        self.assertEqual([], A.comments)
