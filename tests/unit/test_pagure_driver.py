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


from tests.base import ZuulTestCase, simple_layout


class TestPagureDriver(ZuulTestCase):
    config_file = 'zuul-pagure-driver.conf'

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_pull_event(self):

        body = "This is the\nPR body."
        A = self.fake_pagure.openFakePullRequest(
            'org/project', 'master', 'A', body=body)
        self.fake_pagure.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.commit_stop), zuulvars['patchset'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEquals('https://pagure/org/project/pull-request/1',
                          zuulvars['items'][0]['change_url'])
        self.assertEqual(zuulvars["message"], body)
        self.assertEqual(2, len(self.history))
