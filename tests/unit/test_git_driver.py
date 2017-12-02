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


import os
import time
import yaml
import shutil

from tests.base import ZuulTestCase


class TestGitDriver(ZuulTestCase):
    config_file = 'zuul-git-driver.conf'
    tenant_config_file = 'config/git-driver/main.yaml'

    def setup_config(self):
        super(TestGitDriver, self).setup_config()
        self.config.set('connection git', 'baseurl', self.upstream_root)

    def test_basic(self):
        tenant = self.sched.abide.tenants.get('tenant-one')
        # Check that we have the git source for common-config and the
        # gerrit source for the project.
        self.assertEqual('git', tenant.config_projects[0].source.name)
        self.assertEqual('common-config', tenant.config_projects[0].name)
        self.assertEqual('gerrit', tenant.untrusted_projects[0].source.name)
        self.assertEqual('org/project', tenant.untrusted_projects[0].name)

        # The configuration for this test is accessed via the git
        # driver (in common-config), rather than the gerrit driver, so
        # if the job runs, it worked.
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertEqual(len(self.history), 1)
        self.assertEqual(A.reported, 1)

    def test_config_refreshed(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertEqual(len(self.history), 1)
        self.assertEqual(A.reported, 1)
        self.assertEqual(self.history[0].name, 'project-test1')

        # Update zuul.yaml to force a tenant reconfiguration
        path = os.path.join(self.upstream_root, 'common-config', 'zuul.yaml')
        config = yaml.load(open(path, 'r').read())
        change = {
            'name': 'org/project',
            'check': {
                'jobs': [
                    'project-test2'
                ]
            }
        }
        config[4]['project'] = change
        files = {'zuul.yaml': yaml.dump(config)}
        self.addCommitToRepo(
            'common-config', 'Change zuul.yaml configuration', files)

        # Let some time for the tenant reconfiguration to happen
        time.sleep(2)

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertEqual(len(self.history), 2)
        self.assertEqual(A.reported, 1)
        # We make sure the new job has run
        self.assertEqual(self.history[1].name, 'project-test2')

        # Will put that to true in order to push multi common-config commit
        # self.sched.connections.getSource('git').connection.watcher_pause
