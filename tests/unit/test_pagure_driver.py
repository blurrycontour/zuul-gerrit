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

import re

from testtools.matchers import MatchesRegex

from tests.base import ZuulTestCase, simple_layout


class TestPagureDriver(ZuulTestCase):
    config_file = 'zuul-pagure-driver.conf'

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_pull_request_opened(self):

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
        self.assertEqual(1, len(A.comments))
        self.assertThat(
            A.comments[0]['comment'],
            MatchesRegex(r'.*\[project-test1 \]\(.*\).*', re.DOTALL))
        self.assertThat(
            A.comments[0]['comment'],
            MatchesRegex(r'.*\[project-test2 \]\(.*\).*', re.DOTALL))
        self.assertEqual(1, len(A.flags))
        self.assertEqual('success', A.flags[0]['status'])

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_pull_request_updated(self):

        A = self.fake_pagure.openFakePullRequest('org/project', 'master', 'A')
        pr_tip1 = A.commit_stop
        self.fake_pagure.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
            ], ordered=False
        )

        self.fake_pagure.emitEvent(A.getPullRequestUpdatedEvent())
        pr_tip2 = A.commit_stop
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip2},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip2}
            ], ordered=False
        )

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_pull_request_commented(self):

        A = self.fake_pagure.openFakePullRequest('org/project', 'master', 'A')
        self.fake_pagure.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_pagure.emitEvent(
            A.getPullRequestCommentedEvent('I like that change'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_pagure.emitEvent(
            A.getPullRequestCommentedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_ref_updated(self):

        self.fake_pagure.emitEvent(
            self.fake_pagure.getGitReceiveEvent('org/project'))
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))
        self.assertEqual(
            'SUCCESS',
            self.getJobFromHistory('project-post-job').result)
        # TODO: need to verify the zuulvars

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_ref_updated_and_tenant_reconfigure(self):

        pass
