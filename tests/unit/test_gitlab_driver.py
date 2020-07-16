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
import os
import git
import yaml
import socket

import zuul.rpcclient

from tests.base import ZuulTestCase, simple_layout
from tests.base import ZuulWebFixture

from testtools.matchers import MatchesRegex


class TestGitlabWebhook(ZuulTestCase):
    config_file = 'zuul-gitlab-driver.conf'

    def setUp(self):
        super().setUp()

        # Start the web server
        self.web = self.useFixture(
            ZuulWebFixture(self.gearman_server.port,
                           self.config, self.test_root))

        host = '127.0.0.1'
        # Wait until web server is started
        while True:
            port = self.web.port
            try:
                with socket.create_connection((host, port)):
                    break
            except ConnectionRefusedError:
                pass

        self.fake_gitlab.setZuulWebPort(port)

    def tearDown(self):
        super(TestGitlabWebhook, self).tearDown()

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_webhook(self):
        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project', 'master', 'A')
        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent(),
                                   use_zuulweb=False,
                                   project='org/project')
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_webhook_via_zuulweb(self):
        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project', 'master', 'A')
        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent(),
                                   use_zuulweb=True,
                                   project='org/project')
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)


class TestGitlabDriver(ZuulTestCase):
    config_file = 'zuul-gitlab-driver.conf'

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_merge_request_opened(self):

        description = "This is the\nMR description."
        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project', 'master', 'A', description=description)
        self.fake_gitlab.emitEvent(
            A.getMergeRequestOpenedEvent(), project='org/project')
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.sha), zuulvars['patchset'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEquals('https://gitlab/org/project/merge_requests/1',
                          zuulvars['items'][0]['change_url'])
        self.assertEqual(zuulvars["message"], description)
        self.assertEqual(2, len(self.history))
        self.assertEqual(2, len(A.notes))
        self.assertEqual(
            A.notes[0]['body'], "Starting check jobs.")
        self.assertThat(
            A.notes[1]['body'],
            MatchesRegex(r'.*project-test1.*SUCCESS.*', re.DOTALL))
        self.assertThat(
            A.notes[1]['body'],
            MatchesRegex(r'.*project-test2.*SUCCESS.*', re.DOTALL))
        self.assertTrue(A.approved)

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_merge_request_updated(self):

        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')
        mr_tip1_sha = A.sha
        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % mr_tip1_sha},
                {'name': 'project-test2', 'changes': '1,%s' % mr_tip1_sha},
            ], ordered=False
        )

        self.fake_gitlab.emitEvent(A.getMergeRequestUpdatedEvent())
        mr_tip2_sha = A.sha
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % mr_tip1_sha},
                {'name': 'project-test2', 'changes': '1,%s' % mr_tip1_sha},
                {'name': 'project-test1', 'changes': '1,%s' % mr_tip2_sha},
                {'name': 'project-test2', 'changes': '1,%s' % mr_tip2_sha}
            ], ordered=False
        )

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_merge_request_approved(self):

        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')

        self.fake_gitlab.emitEvent(A.getMergeRequestApprovedEvent())
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        self.fake_gitlab.emitEvent(A.getMergeRequestUnapprovedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        job = self.getJobFromHistory('project-test-approval')
        zuulvars = job.parameters['zuul']
        self.assertEqual('check-approval', zuulvars['pipeline'])

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_merge_request_updated_builds_aborted(self):

        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')
        mr_tip1_sha = A.sha

        self.executor_server.hold_jobs_in_build = True

        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()

        self.fake_gitlab.emitEvent(A.getMergeRequestUpdatedEvent())
        mr_tip2_sha = A.sha
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory(
            [
                {'name': 'project-test1', 'result': 'ABORTED',
                 'changes': '1,%s' % mr_tip1_sha},
                {'name': 'project-test2', 'result': 'ABORTED',
                 'changes': '1,%s' % mr_tip1_sha},
                {'name': 'project-test1', 'changes': '1,%s' % mr_tip2_sha},
                {'name': 'project-test2', 'changes': '1,%s' % mr_tip2_sha}
            ], ordered=False
        )

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_merge_request_commented(self):

        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')
        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_gitlab.emitEvent(
            A.getMergeRequestCommentedEvent('I like that change'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        self.fake_gitlab.emitEvent(
            A.getMergeRequestCommentedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_ref_updated(self):

        event = self.fake_gitlab.getPushEvent('org/project')
        expected_newrev = event[1]['after']
        expected_oldrev = event[1]['before']
        self.fake_gitlab.emitEvent(event)
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
            'https://gitlab/org/project/tree/%s' % zuulvars['newrev'],
            zuulvars['change_url'])
        self.assertEqual(expected_newrev, zuulvars['newrev'])
        self.assertEqual(expected_oldrev, zuulvars['oldrev'])

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_ref_created(self):

        self.create_branch('org/project', 'stable-1.0')
        path = os.path.join(self.upstream_root, 'org/project')
        repo = git.Repo(path)
        newrev = repo.commit('refs/heads/stable-1.0').hexsha
        event = self.fake_gitlab.getPushEvent(
            'org/project', branch='refs/heads/stable-1.0',
            before='0' * 40, after=newrev)
        old = self.scheds.first.sched.tenant_last_reconfigured.get(
            'tenant-one', 0)
        self.fake_gitlab.emitEvent(event)
        self.waitUntilSettled()
        new = self.scheds.first.sched.tenant_last_reconfigured.get(
            'tenant-one', 0)
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

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_ref_deleted(self):

        event = self.fake_gitlab.getPushEvent(
            'org/project', 'stable-1.0', after='0' * 40)
        self.fake_gitlab.emitEvent(event)
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_tag_created(self):

        path = os.path.join(self.upstream_root, 'org/project')
        repo = git.Repo(path)
        repo.create_tag('1.0')
        tagsha = repo.tags['1.0'].commit.hexsha
        event = self.fake_gitlab.getGitTagEvent(
            'org/project', '1.0', tagsha)
        self.fake_gitlab.emitEvent(event)
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))
        self.assertEqual(
            'SUCCESS',
            self.getJobFromHistory('project-tag-job').result)
        job = self.getJobFromHistory('project-tag-job')
        zuulvars = job.parameters['zuul']
        self.assertEqual('refs/tags/1.0', zuulvars['ref'])
        self.assertEqual('tag', zuulvars['pipeline'])
        self.assertEqual('project-tag-job', zuulvars['job'])
        self.assertEqual(tagsha, zuulvars['newrev'])

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
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

        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project', 'master', 'A')
        A.addCommit(
            {'.zuul.yaml': yaml.dump(zuul_yaml),
             'job.yaml': playbook}
        )
        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test3').result)

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_ref_updated_and_tenant_reconfigure(self):

        self.waitUntilSettled()
        old = self.scheds.first.sched.tenant_last_reconfigured\
            .get('tenant-one', 0)

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
        event = self.fake_gitlab.getPushEvent('org/project')
        self.fake_gitlab.emitEvent(event)
        self.waitUntilSettled()

        new = self.scheds.first.sched.tenant_last_reconfigured\
            .get('tenant-one', 0)
        # New timestamp should be greater than the old timestamp
        self.assertLess(old, new)

        self.assertHistory(
            [{'name': 'project-post-job'},
             {'name': 'project-post-job2'},
            ], ordered=False
        )

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_client_dequeue_change(self):

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)

        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')

        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()

        client.dequeue(
            tenant='tenant-one',
            pipeline='check',
            project='org/project',
            change='%s,%s' % (A.number, A.sha),
            ref=None)

        self.waitUntilSettled()

        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        check_pipeline = tenant.layout.pipelines['check']
        self.assertEqual(check_pipeline.getAllItems(), [])
        self.assertEqual(self.countJobResults(self.history, 'ABORTED'), 2)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_client_enqueue_change(self):

        A = self.fake_gitlab.openFakeMergeRequest('org/project', 'master', 'A')

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.enqueue(tenant='tenant-one',
                           pipeline='check',
                           project='org/project',
                           trigger='gitlab',
                           change='%s,%s' % (A.number, A.sha))
        self.waitUntilSettled()

        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(r, True)

    @simple_layout('layouts/basic-gitlab.yaml', driver='gitlab')
    def test_client_enqueue_ref(self):
        repo_path = os.path.join(self.upstream_root, 'org/project')
        repo = git.Repo(repo_path)
        headsha = repo.head.commit.hexsha

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.enqueue_ref(
            tenant='tenant-one',
            pipeline='post',
            project='org/project',
            trigger='gitlab',
            ref='master',
            oldrev='1' * 40,
            newrev=headsha)
        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('project-post-job').result,
                         'SUCCESS')
        self.assertEqual(r, True)

    @simple_layout('layouts/crd-gitlab.yaml', driver='gitlab')
    def test_crd_independent(self):

        # Create a change in project1 that a project2 change will depend on
        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project1', 'master', 'A')

        # Create a commit in B that sets the dependency on A
        msg = "Depends-On: %s" % A.url
        B = self.fake_gitlab.openFakeMergeRequest(
            'org/project2', 'master', 'B', description=msg)

        # Make an event to re-use
        self.fake_gitlab.emitEvent(B.getMergeRequestOpenedEvent())
        self.waitUntilSettled()

        # The changes for the job from project2 should include the project1
        # PR content
        changes = self.getJobFromHistory(
            'project2-test', 'org/project2').changes

        self.assertEqual(changes, "%s,%s %s,%s" % (A.number,
                                                   A.sha,
                                                   B.number,
                                                   B.sha))

        # There should be no more changes in the queue
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        self.assertEqual(len(tenant.layout.pipelines['check'].queues), 0)

    @simple_layout('layouts/requirements-gitlab.yaml', driver='gitlab')
    def test_state_require(self):

        A = self.fake_gitlab.openFakeMergeRequest(
            'org/project1', 'master', 'A')

        self.fake_gitlab.emitEvent(A.getMergeRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        # Close the MR
        A.closeMergeRequest()

        # A recheck will not trigger the job
        self.fake_gitlab.emitEvent(
            A.getMergeRequestCommentedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        # Merge the MR
        A.mergeMergeRequest()

        # A recheck will not trigger the job
        self.fake_gitlab.emitEvent(
            A.getMergeRequestCommentedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))

        # Re-open the MR
        A.reopenMergeRequest()

        # A recheck will trigger the job
        self.fake_gitlab.emitEvent(
            A.getMergeRequestCommentedEvent('recheck'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))
