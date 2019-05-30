import re
import time
import yaml

from testtools.matchers import MatchesRegex
import zuul.rpcclient
from tests.base import ZuulTestCase, simple_layout


class TestBitbucketFunctional(ZuulTestCase):
    config_file = 'zuul-bitbucket-driver.conf'

    def pushBranch(self, project, branch, files=[], message=''):
        self.create_branch(project, branch, 'README.md')

        if files:
            self.create_commit(project, head=branch, files=files,
                               message=message)

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_pull_request_opened(self):

        initial_comment = "This is the\nPR description."
        A = self.fake_bitbucket.openFakePullRequest(
            'project/repo', 'A test', 'master', 'foobar',
            description=initial_comment)
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.head), zuulvars['patchset'])
        self.assertEqual('foobar', zuulvars['branch'])
        self.assertEqual(zuulvars["message"], initial_comment)
        self.assertEqual(2, len(self.history))
        self.assertEqual(1, len(A.comments))
        self.assertThat(
            A.comments[0]['text'],
            MatchesRegex(r'.*project-test1.*', re.DOTALL))
        self.assertThat(
            A.comments[0]['text'],
            MatchesRegex(r'.*project-test2.*', re.DOTALL))

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_pull_request_updated(self):

        A = self.fake_bitbucket.openFakePullRequest('project/repo', 'A test',
                                                    'master', 'foobar')
        pr_tip1 = A.head
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual(2, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
            ], ordered=False
        )

        A.update()
        self.fake_bitbucket.runWatcher()
        pr_tip2 = A.head
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

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_pull_request_reviewed(self):
        self.waitUntilSettled()
        time.sleep(2)

        A = self.fake_bitbucket.openFakePullRequest('project/repo', 'A test',
                                                    'master', 'foobar')
        pr_tip1 = A.head
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual(2, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
            ], ordered=False
        )

        A.review()
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual(4, len(self.history))
        self.assertHistory(
            [
                {'name': 'project-test1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-test2', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-gate1', 'changes': '1,%s' % pr_tip1},
                {'name': 'project-gate2', 'changes': '1,%s' % pr_tip1}
            ], ordered=False
        )

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_pull_request_commented(self):

        A = self.fake_bitbucket.openFakePullRequest('project/repo', 'A test',
                                                    'master', 'foobar')
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual(2, len(self.history))

        A.addComment('I like that change.')
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

        A.addComment('recheck')
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()
        self.assertEqual(4, len(self.history))

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
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

        A = self.fake_bitbucket.openFakePullRequest(
            'project/repo', 'A test', 'master', 'foobar')
        A.addCommit(
            {'.zuul.yaml': yaml.dump(zuul_yaml),
             'job.yaml': playbook}
        )
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test3').result)

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_branch_updated(self):
        self.waitUntilSettled()
        time.sleep(1)

        self.pushBranch('project/repo',
                        'testing')

        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()
        self.assertEqual(1, len(self.history))
        self.assertEqual(
            'SUCCESS',
            self.getJobFromHistory('project-post-job').result)

        job = self.getJobFromHistory('project-post-job')
        zuulvars = job.parameters['zuul']
        self.assertEqual('refs/heads/testing', zuulvars['ref'])
        self.assertEqual('post', zuulvars['pipeline'])
        self.assertEqual('project-post-job', zuulvars['job'])
        self.assertEqual('testing', zuulvars['branch'])

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_branch_updated_and_tenant_reconfigure(self):

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
        self.pushBranch(
            'project/repo', 'testing',
            {'.zuul.yaml': yaml.dump(zuul_yaml),
             'job.yaml': playbook},
            message='Add InRepo configuration'
        )
        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        new = self.sched.tenant_last_reconfigured.get('tenant-one', 0)
        # New timestamp should be greater than the old timestamp
        self.assertLess(old, new)

        self.assertHistory(
            [
                {'name': 'project-post-job'},
                {'name': 'project-post-job2'},
            ], ordered=False
        )

    # FIXME test_ref_updated & test_ref_updated_and_tenant_reconfigure

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_client_dequeue_change(self):

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)

        self.executor_server.hold_jobs_in_build = True
        A = self.fake_bitbucket.openFakePullRequest('project/repo', 'A test',
                                                    'master', 'foobar')

        self.fake_bitbucket.runWatcher()
        self.waitUntilSettled()

        client.dequeue(
            tenant='tenant-one',
            pipeline='check',
            project='project/repo',
            change='%i,%s' % (A.number, A.head),
            ref=None)

        self.waitUntilSettled()

        tenant = self.sched.abide.tenants.get('tenant-one')
        check_pipeline = tenant.layout.pipelines['check']
        self.assertEqual(check_pipeline.getAllItems(), [])
        self.assertEqual(self.countJobResults(self.history, 'ABORTED'), 2)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

    @simple_layout('layouts/basic-bitbucket.yaml', driver='bitbucket')
    def test_client_enqueue_change(self):

        A = self.fake_bitbucket.openFakePullRequest('project/repo', 'A test',
                                                    'master', 'foobar')

        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.enqueue(tenant='tenant-one',
                           pipeline='check',
                           project='project/repo',
                           trigger='bitbucket',
                           change='%s,%s' % (A.number, A.head))
        self.waitUntilSettled()

        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(r, True)
