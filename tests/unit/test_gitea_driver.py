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

import re
import socket

from zuul.lib import strings
from tests.base import ZuulTestCase, simple_layout
from tests.base import ZuulWebFixture


class TestGiteaDriver(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_opened(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        expected_pr_message = "%s\n\n%s" % (A.subject, initial_comment)
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.head_sha), zuulvars['patchset'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEquals('https://fakegitea.com/org/project/pulls/1',
                          zuulvars['items'][0]['change_url'])
        self.assertEqual(zuulvars["message"],
                         strings.b64encode(expected_pr_message))
        self.assertEqual(2, len(self.history))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_closed(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')

        self.fake_gitea.emitEvent(A.getPullRequestClosedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_reopened(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        expected_pr_message = "%s\n\n%s" % (A.subject, initial_comment)
        self.fake_gitea.emitEvent(A.getPullRequestReopenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.head_sha), zuulvars['patchset'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEquals('https://fakegitea.com/org/project/pulls/1',
                          zuulvars['items'][0]['change_url'])
        self.assertEqual(zuulvars["message"],
                         strings.b64encode(expected_pr_message))
        self.assertEqual(2, len(self.history))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_edited(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestEditedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_updated(self):

        A = self.fake_gitea.openFakePullRequest('org/project', 'master', 'A')
        pr_tip1 = A.head_sha
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
            ], ordered=False
        )

        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        pr_tip2 = A.head_sha
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

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_updated_builds_aborted(self):

        A = self.fake_gitea.openFakePullRequest('org/project', 'master', 'A')
        pr_tip1 = A.head_sha

        self.executor_server.hold_jobs_in_build = True

        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        pr_tip2 = A.head_sha
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory(
            [
                {'name': 'project-test1', 'result': 'ABORTED',
                 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'result': 'ABORTED',
                 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip2},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip2}
            ], ordered=False
        )

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_commented(self):

        A = self.fake_gitea.openFakePullRequest('org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestCommentCreatedEvent('I like that change'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestCommentCreatedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestCommentDeletedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestInitialCommentEvent('Initial comment edited'))
        self.waitUntilSettled()
        self.assertEqual(6, len(self.history))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_reporter_comment(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        p1 = self.getJobFromHistory('project-test1')
        p2 = self.getJobFromHistory('project-test2')

        self.assertEqual('SUCCESS', p1.result)
        self.assertEqual('SUCCESS', p2.result)

        # TODO(gtema): how to get fake build duration?
        expected_comment = re.compile(
            (
                rf"Build succeeded.*"
                rf"- \[project-test1 \]\(build/{p1.uuid}\): {p1.result} in .*"
                rf"- \[project-test2 \]\(build/{p2.uuid}\): {p2.result} in .*"
            ),
            flags=re.DOTALL
        )
        # Verify start reporter
        self.assertIn('Starting check jobs.', A.comments)
        # Verify success reporter
        found_match = False
        for comment in A.comments:
            if expected_comment.search(comment):
                found_match = True
                break
        self.assertTrue(found_match)
        self.assertEqual(2, len(A.comments))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_reporter_status(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        p1 = self.getJobFromHistory('project-test1')
        p2 = self.getJobFromHistory('project-test2')

        self.assertEqual('SUCCESS', p1.result)
        self.assertEqual('SUCCESS', p2.result)

        self.assertDictEqual(
            {
                'pending': {'context': 'tenant-one/check'},
                'success': {'context': 'tenant-one/check'}
            },
            self.fake_gitea.statuses[A.head_sha])


class TestGiteaWebhook(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'

    def setUp(self):
        super(TestGiteaWebhook, self).setUp()
        # Start the web server
        self.web = self.useFixture(
            ZuulWebFixture(self.changes, self.config,
                           self.additional_event_queues, self.upstream_root,
                           self.poller_events,
                           self.git_url_with_auth, self.addCleanup,
                           self.test_root))

        host = '127.0.0.1'
        # Wait until web server is started
        while True:
            port = self.web.port
            try:
                with socket.create_connection((host, port)):
                    break
            except ConnectionRefusedError:
                pass

        self.fake_gitea.setZuulWebPort(port)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_webhook(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent(),
                                  use_zuulweb=False,
                                  project='org/project')
        self.waitUntilSettled()
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_webhook_via_zuulweb(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent(),
                                  use_zuulweb=True,
                                  project='org/project')
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
