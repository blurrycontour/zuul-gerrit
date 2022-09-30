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

import git
import os
import re
import socket
import yaml

from zuul.lib import strings
from zuul.zk.layout import LayoutState

from tests.base import ZuulTestCase, simple_layout
from tests.base import ZuulWebFixture

EMPTY_LAYOUT_STATE = LayoutState("", "", 0, None, {}, -1)


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

        # Simple "edited" event does not trigger job
        self.assertEqual(0, len(self.history))

        self.fake_gitea.emitEvent(A.getPullRequestEditedEvent({
            'title': {'from': 'old'}
        }))
        self.waitUntilSettled()
        # Changing title event does not trigger job
        self.assertEqual(0, len(self.history))

        self.fake_gitea.emitEvent(A.getPullRequestEditedEvent(
            changes={'body': {'from': 'old'}}))
        self.waitUntilSettled()
        # Changing pr message (initial comment) by default does not trigger job
        self.assertEqual(0, len(self.history))

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

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_label_updated(self):

        A = self.fake_gitea.openFakePullRequest('org/project', 'master', 'A')

        self.fake_gitea.emitEvent(
            A.getPullRequestLabelUpdatedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

    @simple_layout('layouts/reviews-gitea.yaml', driver='gitea')
    def test_pull_request_reviewed(self):

        A = self.fake_gitea.openFakePullRequest('org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestReviewRejectedEvent("I don't like that change"))
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestReviewApprovedEvent("I like that change"))
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        self.fake_gitea.emitEvent(
            A.getPullRequestReviewCommentEvent("mergeme"))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

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

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_with_dyn_reconf(self):

        zuul_yaml = [
            {'job': {
                'name': 'project-test3',
                'run': 'job.yaml'
            }},
            {'project': {
                'check': {
                    'jobs': [
                        'project-test3'
                    ]
                }
            }}
        ]
        playbook = "- hosts: all\n  tasks: []"

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        A.addCommit(
            {'.zuul.yaml': yaml.dump(zuul_yaml),
             'job.yaml': playbook}
        )
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test3').result)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_ref_updated(self):

        event = self.fake_gitea.getGitPushEvent('org/project')
        expected_newrev = event[2]['after']
        expected_oldrev = event[2]['before']
        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))
        self.assertEqual(
            'SUCCESS',
            self.getJobFromHistory('project-post-job').result)

        job = self.getJobFromHistory('project-post-job')
        zuulvars = job.parameters['zuul']
        self.assertEqual('refs/heads/master', zuulvars['ref'])
        self.assertEqual('post', zuulvars['pipeline'])
        self.assertEqual('project-post-job', zuulvars['job'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEqual(
            'https://fakegitea.com/org/project/commit/%s' % zuulvars['newrev'],
            zuulvars['change_url'])
        self.assertEqual(expected_newrev, zuulvars['newrev'])
        self.assertEqual(expected_oldrev, zuulvars['oldrev'])

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_ref_created(self):

        self.create_branch('org/project', 'stable-1.0')
        path = os.path.join(self.upstream_root, 'org/project')
        repo = git.Repo(path)
        newrev = repo.commit('refs/heads/stable-1.0').hexsha
        event = self.fake_gitea.getGitBranchEvent(
            'org/project', 'stable-1.0', 'create', newrev)
        old = self.scheds.first.sched.tenant_layout_state.get(
            'tenant-one', EMPTY_LAYOUT_STATE)
        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()
        new = self.scheds.first.sched.tenant_layout_state.get(
            'tenant-one', EMPTY_LAYOUT_STATE)
        # New timestamp should be greater than the old timestamp
        self.assertLess(old, new)
        self.assertEqual(1, len(self.history))
        self.assertEqual(
            'SUCCESS',
            self.getJobFromHistory('project-post-job').result)
        job = self.getJobFromHistory('project-post-job')
        zuulvars = job.parameters['zuul']
        self.assertEqual('refs/heads/stable-1.0', zuulvars['ref'])
        self.assertEqual('post', zuulvars['pipeline'])
        self.assertEqual('project-post-job', zuulvars['job'])
        self.assertEqual('stable-1.0', zuulvars['branch'])
        self.assertEqual(newrev, zuulvars['newrev'])

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_ref_deleted(self):

        event = self.fake_gitea.getGitBranchEvent(
            'org/project', 'stable-1.0', type='delete', rev='0' * 40)
        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_ref_updated_and_tenant_reconfigure(self):

        self.waitUntilSettled()
        old = self.scheds.first.sched.tenant_layout_state.get(
            'tenant-one', EMPTY_LAYOUT_STATE)

        zuul_yaml = [
            {'job': {
                'name': 'project-post-job2',
                'run': 'job.yaml'
            }},
            {'project': {
                'post': {
                    'jobs': [
                        'project-post-job2'
                    ]
                }
            }}
        ]
        playbook = "- hosts: all\n  tasks: []"
        self.create_commit(
            'org/project',
            {'.zuul.yaml': yaml.dump(zuul_yaml),
             'job.yaml': playbook},
            message='Add InRepo configuration'
        )
        event = self.fake_gitea.getGitPushEvent('org/project')
        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()

        new = self.scheds.first.sched.tenant_layout_state.get(
            'tenant-one', EMPTY_LAYOUT_STATE)
        # New timestamp should be greater than the old timestamp
        self.assertLess(old, new)

        self.assertHistory(
            [{'name': 'project-post-job'},
             {'name': 'project-post-job2'},
            ], ordered=False
        )

    @simple_layout('layouts/gate-gitea.yaml', driver='gitea')
    def test_pull_request_merged(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        expected_pr_message = "%s\n\n%s" % (A.subject, initial_comment)
        A.addReview(state='APPROVED')
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
        self.assertTrue(A.is_merged)
        self.assertEqual(A.merge_title, A.subject)
        self.assertEqual(A.merge_message, "Reviewed-by: tester <fake_mail>")
        self.assertEqual(A.merge_mode, "merge")

    @simple_layout('layouts/gate-gitea-squash.yaml', driver='gitea')
    def test_pull_request_merged_squash(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        A.addReview(state='APPROVED')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual(2, len(self.history))
        self.assertTrue(A.is_merged)
        self.assertEqual(A.merge_title, A.subject)
        self.assertEqual(A.merge_message, "Reviewed-by: tester <fake_mail>")
        self.assertEqual(A.merge_mode, "squash")

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_dequeue_pull_abandoned(self):
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.fake_gitea.emitEvent(A.getPullRequestClosedEvent())
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(2, len(self.history))
        self.assertEqual(2, self.countJobResults(self.history, 'ABORTED'))

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_dequeue_updated(self):
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(4, len(self.history))
        self.assertEqual(2, self.countJobResults(self.history, 'ABORTED'))

    @simple_layout('layouts/requirements-gitea.yaml', driver='gitea')
    def test_require_state(self):
        A = self.fake_gitea.openFakePullRequest(
            'org/project1', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        # Close PR
        A.closePullRequest()

        # A recheck on closed PR does not trigger the job
        self.fake_gitea.emitEvent(
            A.getPullRequestCommentCreatedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        # Reopen PR
        A.reopenPullRequest()

        # A recheck on reopened does trigger the job
        self.fake_gitea.emitEvent(
            A.getPullRequestCommentCreatedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        # Merge it
        A.mergePullRequest()

        # A recheck on merged PR does not trigger the job
        self.fake_gitea.emitEvent(
            A.getPullRequestCommentCreatedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

    @simple_layout('layouts/requirements-gitea.yaml', driver='gitea')
    def test_require_approval(self):
        A = self.fake_gitea.openFakePullRequest(
            'org/project2', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

        A.addReview(state='APPROVED')
        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

    @simple_layout('layouts/requirements-gitea.yaml', driver='gitea')
    def test_require_label(self):
        A = self.fake_gitea.openFakePullRequest(
            'org/project3', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

        # Only one required label is there
        A.labels = ['gateit', 'useless']
        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

        # Only one required label is there
        A.labels = ['gateit', 'another_label']
        self.fake_gitea.emitEvent(A.getPullRequestUpdatedEvent())
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))


class TestGiteaWebhook(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'

    def setUp(self):
        super().setUp()
        # Start the web server
        self.web = self.useFixture(
            ZuulWebFixture(self.config, self.test_config,
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
