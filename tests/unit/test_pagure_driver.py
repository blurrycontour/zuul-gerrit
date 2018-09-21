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
import yaml
import time

from testtools.matchers import MatchesRegex

import zuul.rpcclient

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
        self.assertEqual(2, len(A.comments))
        self.assertEqual(
            A.comments[0]['comment'], "Starting check jobs.")
        self.assertThat(
            A.comments[1]['comment'],
            MatchesRegex(r'.*\[project-test1 \]\(.*\).*', re.DOTALL))
        self.assertThat(
            A.comments[1]['comment'],
            MatchesRegex(r'.*\[project-test2 \]\(.*\).*', re.DOTALL))
        self.assertEqual(2, len(A.flags))
        self.assertEqual('success', A.flags[0]['status'])
        self.assertEqual('pending', A.flags[1]['status'])

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

        A = self.fake_pagure.openFakePullRequest(
            'org/project', 'master', 'A')
        A.addCommit(
            {'.zuul.yaml': yaml.dump(zuul_yaml),
            'job.yaml': playbook}
        )
        self.fake_pagure.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test3').result)

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_ref_updated(self):

        event = self.fake_pagure.getGitReceiveEvent('org/project')
        expected_newrev = event[1]['msg']['stop_commit']
        self.fake_pagure.emitEvent(event)
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
            'https://pagure/org/project/commit/%s' % zuulvars['newrev'],
            zuulvars['change_url'])
        self.assertEqual(expected_newrev, zuulvars['newrev'])

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_ref_updated_and_tenant_reconfigure(self):

        self.waitUntilSettled()
        old = self.sched.tenant_last_reconfigured.get('tenant-one', 0)
        time.sleep(1)

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
        event = self.fake_pagure.getGitReceiveEvent('org/project')
        self.fake_pagure.emitEvent(event)
        self.waitUntilSettled()

        new = self.sched.tenant_last_reconfigured.get('tenant-one', 0)
        # New timestamp should be greater than the old timestamp
        self.assertLess(old, new)

        self.assertHistory(
            [{'name': 'project-post-job'},
             {'name': 'project-post-job2'},
            ], ordered=False
        )

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_client_dequeue_change_pagure(self):

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)

        self.executor_server.hold_jobs_in_build = True
        A = self.fake_pagure.openFakePullRequest('org/project', 'master', 'A')

        self.fake_pagure.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        client.dequeue(
            tenant='tenant-one',
            pipeline='check',
            project='org/project',
            change='%s,%s' % (A.number, A.commit_stop),
            ref=None)

        self.waitUntilSettled()

        tenant = self.sched.abide.tenants.get('tenant-one')
        check_pipeline = tenant.layout.pipelines['check']
        self.assertEqual(check_pipeline.getAllItems(), [])
        self.assertEqual(self.countJobResults(self.history, 'ABORTED'), 2)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

    @simple_layout('layouts/basic-pagure.yaml', driver='pagure')
    def test_client_enqueue_change_pagure(self):

        A = self.fake_pagure.openFakePullRequest('org/project', 'master', 'A')

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.enqueue(tenant='tenant-one',
                           pipeline='check',
                           project='org/project',
                           trigger='pagure',
                           change='%s,%s' % (A.number, A.commit_stop))
        self.waitUntilSettled()

        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(r, True)
