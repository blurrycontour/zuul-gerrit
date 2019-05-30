#  import re2

#  from testtools.matchers import MatchesRegex

import yaml

import zuul.rpcclient

from tests.base import ZuulTestCase, simple_layout


class TestBitbucketFunctional(ZuulTestCase):
    config_file = 'zuul-bitbucket-driver.conf'

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
        #  self.assertEqual(2, len(A.comments))
        #  self.assertEqual(
        #    A.comments[0]['comment'], "Starting check jobs.")
        #  self.assertThat(
        #    A.comments[1]['comment'],
        #    MatchesRegex(r'.*\[project-test1 \]\(.*\).*', re2.DOTALL))
        #  self.assertThat(
        #    A.comments[1]['comment'],
        #    MatchesRegex(r'.*\[project-test2 \]\(.*\).*', re2.DOTALL))
        #  self.assertEqual(2, len(A.flags))
        # self.assertEqual('success', A.flags[0]['status'])
        # self.assertEqual('pending', A.flags[1]['status'])

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
            project='org/project',
            change='%s,%s' % (A.number, A.head),
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
                           project='org/project',
                           trigger='bitbucket',
                           change='%s,%s' % (A.number, A.commit_stop))
        self.waitUntilSettled()

        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(r, True)
