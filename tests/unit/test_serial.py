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
    ZuulTestCase,
    simple_layout,
)


class TestDeployWindow(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'

    @simple_layout('layouts/serial.yaml')
    def test_deploy_window(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.setMerged()
        self.fake_gerrit.addEvent(A.getChangeMergedEvent())
        self.waitUntilSettled()
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')
        B.setMerged()
        self.fake_gerrit.addEvent(B.getChangeMergedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 2)
        self.assertTrue(self.builds[0].hasChanges(A))
        self.assertTrue(self.builds[1].hasChanges(A))
        self.assertFalse(self.builds[0].hasChanges(B))
        self.assertFalse(self.builds[1].hasChanges(B))

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 2)
        self.assertTrue(self.builds[0].hasChanges(A))
        self.assertTrue(self.builds[1].hasChanges(A))
        self.assertTrue(self.builds[0].hasChanges(B))
        self.assertTrue(self.builds[1].hasChanges(B))

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 1)
        self.assertEqual(B.reported, 1)
        self.assertHistory([
            dict(name='job1', result='SUCCESS', changes='1,1'),
            dict(name='job2', result='SUCCESS', changes='1,1'),
            dict(name='job1', result='SUCCESS', changes='2,1'),
            dict(name='job2', result='SUCCESS', changes='2,1'),
        ], ordered=False)
