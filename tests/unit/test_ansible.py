# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

import io
import json
import logging
import os
import textwrap

import zuul.configloader
from tests.base import (
    AnsibleZuulTestCase,
    FIXTURE_DIR,
    iterate_timeout,
)


class TestMultipleTenants(AnsibleZuulTestCase):
    # A temporary class to hold new tests while others are disabled

    tenant_config_file = 'config/multi-tenant/main.yaml'

    def test_multiple_tenants(self):
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('project1-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('python27').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2,
                         "A should report start and success")
        self.assertIn('tenant-one-gate', A.messages[1],
                      "A should transit tenant-one gate")
        self.assertNotIn('tenant-two-gate', A.messages[1],
                         "A should *not* transit tenant-two gate")

        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('python27',
                                                'org/project2').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project2-test1').result,
                         'SUCCESS')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertEqual(B.reported, 2,
                         "B should report start and success")
        self.assertIn('tenant-two-gate', B.messages[1],
                      "B should transit tenant-two gate")
        self.assertNotIn('tenant-one-gate', B.messages[1],
                         "B should *not* transit tenant-one gate")

        self.assertEqual(A.reported, 2, "Activity in tenant two should"
                         "not affect tenant one")


class TestJobContamination(AnsibleZuulTestCase):

    config_file = 'zuul-connections-gerrit-and-github.conf'
    tenant_config_file = 'config/zuul-job-contamination/main.yaml'

    def test_job_contamination_playbooks(self):
        conf = textwrap.dedent(
            """
            - job:
                name: base
                post-run:
                  - playbooks/something-new.yaml
                parent: null
                vars:
                  basevar: basejob
            """)

        file_dict = {'zuul.d/jobs.yaml': conf}
        A = self.fake_github.openFakePullRequest(
            'org/global-config', 'master', 'A', files=file_dict)
        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        B = self.fake_github.openFakePullRequest('org/project1', 'master', 'A')
        self.fake_github.emitEvent(B.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        statuses_b = self.fake_github.getCommitStatuses(
            'org/project1', B.head_sha)

        self.assertEqual(len(statuses_b), 1)

        # B should not be affected by the A PR
        self.assertEqual('success', statuses_b[0]['state'])

    def test_job_contamination_vars(self):
        conf = textwrap.dedent(
            """
            - job:
                name: base
                parent: null
                vars:
                  basevar: basejob-modified
            """)

        file_dict = {'zuul.d/jobs.yaml': conf}
        A = self.fake_github.openFakePullRequest(
            'org/global-config', 'master', 'A', files=file_dict)
        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        B = self.fake_github.openFakePullRequest('org/project1', 'master', 'A')
        self.fake_github.emitEvent(B.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        statuses_b = self.fake_github.getCommitStatuses(
            'org/project1', B.head_sha)

        self.assertEqual(len(statuses_b), 1)

        # B should not be affected by the A PR
        self.assertEqual('success', statuses_b[0]['state'])


class FunctionalAnsibleMixIn(object):
    # A temporary class to hold new tests while others are disabled

    tenant_config_file = 'config/ansible/main.yaml'
    # This should be overriden in child classes.
    ansible_version = '2.9'

    def test_playbook(self):
        # This test runs a bit long and needs extra time.
        self.wait_timeout = 300
        # Keep the jobdir around so we can inspect contents if an
        # assert fails.
        self.executor_server.keep_jobdir = True
        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        # Add a site variables file, used by check-vars
        path = os.path.join(FIXTURE_DIR, 'config', 'ansible',
                            'variables.yaml')
        self.config.set('executor', 'variables', path)
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        build_timeout = self.getJobFromHistory('timeout', result='TIMED_OUT')
        with self.jobLog(build_timeout):
            post_flag_path = os.path.join(
                self.jobdir_root, build_timeout.uuid + '.post.flag')
            self.assertTrue(os.path.exists(post_flag_path))
        build_post_timeout = self.getJobFromHistory('post-timeout')
        with self.jobLog(build_post_timeout):
            self.assertEqual(build_post_timeout.result, 'POST_FAILURE')
        build_faillocal = self.getJobFromHistory('faillocal')
        with self.jobLog(build_faillocal):
            self.assertEqual(build_faillocal.result, 'FAILURE')
        build_failpost = self.getJobFromHistory('failpost')
        with self.jobLog(build_failpost):
            self.assertEqual(build_failpost.result, 'POST_FAILURE')
        build_check_vars = self.getJobFromHistory('check-vars')
        with self.jobLog(build_check_vars):
            self.assertEqual(build_check_vars.result, 'SUCCESS')
        build_check_hostvars = self.getJobFromHistory('check-hostvars')
        with self.jobLog(build_check_hostvars):
            self.assertEqual(build_check_hostvars.result, 'SUCCESS')
        build_check_secret_names = self.getJobFromHistory('check-secret-names')
        with self.jobLog(build_check_secret_names):
            self.assertEqual(build_check_secret_names.result, 'SUCCESS')
        build_hello = self.getJobFromHistory('hello-world')
        with self.jobLog(build_hello):
            self.assertEqual(build_hello.result, 'SUCCESS')
        build_add_host = self.getJobFromHistory('add-host')
        with self.jobLog(build_add_host):
            self.assertEqual(build_add_host.result, 'SUCCESS')
        build_multiple_child = self.getJobFromHistory('multiple-child')
        with self.jobLog(build_multiple_child):
            self.assertEqual(build_multiple_child.result, 'SUCCESS')
        build_multiple_child_no_run = self.getJobFromHistory(
            'multiple-child-no-run')
        with self.jobLog(build_multiple_child_no_run):
            self.assertEqual(build_multiple_child_no_run.result, 'SUCCESS')
        build_multiple_run = self.getJobFromHistory('multiple-run')
        with self.jobLog(build_multiple_run):
            self.assertEqual(build_multiple_run.result, 'SUCCESS')
        build_multiple_run_failure = self.getJobFromHistory(
            'multiple-run-failure')
        with self.jobLog(build_multiple_run_failure):
            self.assertEqual(build_multiple_run_failure.result, 'FAILURE')
        build_python27 = self.getJobFromHistory('python27')
        with self.jobLog(build_python27):
            self.assertEqual(build_python27.result, 'SUCCESS')
            flag_path = os.path.join(self.jobdir_root,
                                     build_python27.uuid + '.flag')
            self.assertTrue(os.path.exists(flag_path))
            copied_path = os.path.join(self.jobdir_root, build_python27.uuid +
                                       '.copied')
            self.assertTrue(os.path.exists(copied_path))
            failed_path = os.path.join(self.jobdir_root, build_python27.uuid +
                                       '.failed')
            self.assertFalse(os.path.exists(failed_path))
            pre_flag_path = os.path.join(
                self.jobdir_root, build_python27.uuid + '.pre.flag')
            self.assertTrue(os.path.exists(pre_flag_path))
            post_flag_path = os.path.join(
                self.jobdir_root, build_python27.uuid + '.post.flag')
            self.assertTrue(os.path.exists(post_flag_path))
            bare_role_flag_path = os.path.join(self.jobdir_root,
                                               build_python27.uuid +
                                               '.bare-role.flag')
            self.assertTrue(os.path.exists(bare_role_flag_path))
            secrets_path = os.path.join(self.jobdir_root,
                                        build_python27.uuid + '.secrets')
            with open(secrets_path) as f:
                self.assertEqual(f.read(), "test-username test-password")

            msg = A.messages[0]
            success = "{} https://success.example.com/zuul-logs/{}"
            fail = "{} https://failure.example.com/zuul-logs/{}"
            self.assertIn(success.format("python27", build_python27.uuid), msg)
            self.assertIn(fail.format("faillocal", build_faillocal.uuid), msg)
            self.assertIn(success.format("check-vars",
                                         build_check_vars.uuid), msg)
            self.assertIn(success.format("hello-world", build_hello.uuid), msg)
            self.assertIn(fail.format("timeout", build_timeout.uuid), msg)
            self.assertIn(fail.format("failpost", build_failpost.uuid), msg)

    def test_repo_ansible(self):
        A = self.fake_gerrit.addFakeChange('org/ansible', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 1,
                         "A should report success")
        self.assertHistory([
            dict(name='hello-ansible', result='SUCCESS', changes='1,1'),
        ])

    def _add_job(self, job_name):
        conf = textwrap.dedent(
            """
            - job:
                name: {job_name}
                run: playbooks/{job_name}.yaml
                ansible-version: {ansible_version}

            - project:
                check:
                  jobs:
                    - {job_name}
            """.format(job_name=job_name,
                       ansible_version=self.ansible_version))

        file_dict = {'.zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange('org/plugin-project', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

    def _test_plugins(self, plugin_tests):
        # This test runs a bit long and needs extra time.
        self.wait_timeout = 180

        # Keep the jobdir around so we can inspect contents if an
        # assert fails.
        self.executor_server.keep_jobdir = True
        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True

        count = 0

        # Kick off all test jobs in parallel
        for job_name, result in plugin_tests:
            count += 1
            self._add_job(job_name)
        # Wait for all jobs to complete
        self.waitUntilSettled()

        # Check the correct number of jobs ran
        self.assertEqual(count, len(self.history))
        # Check the job results
        for job_name, result in plugin_tests:
            build = self.getJobFromHistory(job_name)
            with self.jobLog(build):
                self.assertEqual(build.result, result)

        # TODOv3(jeblair): parse the ansible output and verify we're
        # getting the exception we expect.

    def test_plugins_1(self):
        '''
        Split plugin tests to avoid timeouts and exceeding subunit
        report lengths.
        '''
        plugin_tests = [
            ('passwd', 'FAILURE'),
            ('cartesian', 'SUCCESS'),
            ('consul_kv', 'FAILURE'),
            ('credstash', 'FAILURE'),
            ('csvfile_good', 'SUCCESS'),
            ('csvfile_bad', 'FAILURE'),
            ('uri_bad_path', 'FAILURE'),
            ('uri_bad_scheme', 'FAILURE'),
        ]
        self._test_plugins(plugin_tests)

    def test_plugins_2(self):
        '''
        Split plugin tests to avoid timeouts and exceeding subunit
        report lengths.
        '''
        plugin_tests = [
            ('block_local_override', 'FAILURE'),
            ('file_local_good', 'SUCCESS'),
            ('file_local_bad', 'FAILURE'),
            ('zuul_return', 'SUCCESS'),
            ('password_create_good', 'SUCCESS'),
            ('password_null_good', 'SUCCESS'),
            ('password_read_good', 'SUCCESS'),
            ('password_create_bad', 'FAILURE'),
            ('password_read_bad', 'FAILURE'),
        ]
        self._test_plugins(plugin_tests)


class TestAnsible26(AnsibleZuulTestCase, FunctionalAnsibleMixIn):
    ansible_version = '2.6'


class TestAnsible27(AnsibleZuulTestCase, FunctionalAnsibleMixIn):
    ansible_version = '2.7'


class TestAnsible28(AnsibleZuulTestCase, FunctionalAnsibleMixIn):
    ansible_version = '2.8'


class TestAnsible29(AnsibleZuulTestCase, FunctionalAnsibleMixIn):
    ansible_version = '2.9'


class TestPrePlaybooks(AnsibleZuulTestCase):
    # A temporary class to hold new tests while others are disabled

    tenant_config_file = 'config/pre-playbook/main.yaml'

    def test_pre_playbook_fail(self):
        # Test that we run the post playbooks (but not the actual
        # playbook) when a pre-playbook fails.
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        build = self.getJobFromHistory('python27')
        self.assertIsNone(build.result)
        self.assertIn('RETRY_LIMIT', A.messages[0])
        flag_path = os.path.join(self.test_root, build.uuid +
                                 '.main.flag')
        self.assertFalse(os.path.exists(flag_path))
        pre_flag_path = os.path.join(self.test_root, build.uuid +
                                     '.pre.flag')
        self.assertFalse(os.path.exists(pre_flag_path))
        post_flag_path = os.path.join(
            self.jobdir_root, build.uuid + '.post.flag')
        self.assertTrue(os.path.exists(post_flag_path),
                        "The file %s should exist" % post_flag_path)

    def test_post_playbook_fail_autohold(self):
        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.autohold('tenant-one', 'org/project3', 'python27-node-post',
                            "", "", "reason text", 1)
        self.assertTrue(r)

        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        build = self.getJobFromHistory('python27-node-post')
        self.assertEqual(build.result, 'POST_FAILURE')

        # Check nodepool for a held node
        held_node = None
        for node in self.fake_nodepool.getNodes():
            if node['state'] == zuul.model.STATE_HOLD:
                held_node = node
                break
        self.assertIsNotNone(held_node)
        # Validate node has recorded the failed job
        self.assertEqual(
            held_node['hold_job'],
            " ".join(['tenant-one',
                      'review.example.com/org/project3',
                      'python27-node-post', '.*'])
        )
        self.assertEqual(held_node['comment'], "reason text")

    def test_pre_playbook_fail_autohold(self):
        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.autohold('tenant-one', 'org/project2', 'python27-node',
                            "", "", "reason text", 1)
        self.assertTrue(r)

        A = self.fake_gerrit.addFakeChange('org/project2', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        build = self.getJobFromHistory('python27-node')
        self.assertIsNone(build.result)
        self.assertIn('RETRY_LIMIT', A.messages[0])

        # Check nodepool for a held node
        held_node = None
        for node in self.fake_nodepool.getNodes():
            if node['state'] == zuul.model.STATE_HOLD:
                held_node = node
                break
        self.assertIsNotNone(held_node)
        # Validate node has recorded the failed job
        self.assertEqual(
            held_node['hold_job'],
            " ".join(['tenant-one',
                      'review.example.com/org/project2',
                      'python27-node', '.*'])
        )
        self.assertEqual(held_node['comment'], "reason text")


class TestPostPlaybooks(AnsibleZuulTestCase):
    tenant_config_file = 'config/post-playbook/main.yaml'

    def test_post_playbook_abort(self):
        # Test that when we abort a job in the post playbook, that we
        # don't send back POST_FAILURE.
        self.executor_server.verbose = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        for _ in iterate_timeout(60, 'job started'):
            if len(self.builds):
                break
        build = self.builds[0]

        post_start = os.path.join(self.jobdir_root, build.uuid +
                                  '.post_start.flag')
        for _ in iterate_timeout(60, 'job post running'):
            if os.path.exists(post_start):
                break
        # The post playbook has started, abort the job
        self.fake_gerrit.addEvent(A.getChangeAbandonedEvent())
        self.waitUntilSettled()

        build = self.getJobFromHistory('python27')
        self.assertEqual('ABORTED', build.result)

        post_end = os.path.join(self.jobdir_root, build.uuid +
                                '.post_end.flag')
        self.assertTrue(os.path.exists(post_start))
        self.assertFalse(os.path.exists(post_end))


class TestCleanupPlaybooks(AnsibleZuulTestCase):
    tenant_config_file = 'config/cleanup-playbook/main.yaml'

    def test_cleanup_playbook_success(self):
        # Test that the cleanup run is performed
        self.executor_server.verbose = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        for _ in iterate_timeout(60, 'job started'):
            if len(self.builds):
                break
        build = self.builds[0]

        post_start = os.path.join(self.jobdir_root, build.uuid +
                                  '.post_start.flag')
        for _ in iterate_timeout(60, 'job post running'):
            if os.path.exists(post_start):
                break
        with open(os.path.join(self.jobdir_root, build.uuid, 'test_wait'),
                  "w") as of:
            of.write("continue")
        self.waitUntilSettled()

        build = self.getJobFromHistory('python27')
        self.assertEqual('SUCCESS', build.result)
        cleanup_flag = os.path.join(self.jobdir_root, build.uuid +
                                    '.cleanup.flag')
        self.assertTrue(os.path.exists(cleanup_flag))
        with open(cleanup_flag) as f:
            self.assertEqual('True', f.readline())

    def test_cleanup_playbook_failure(self):
        # Test that the cleanup run is performed
        self.executor_server.verbose = True

        in_repo_conf = textwrap.dedent(
            """
            - project:
                check:
                  jobs:
                    - python27-failure
            """)
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A',
                                           files={'.zuul.yaml': in_repo_conf})
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        for _ in iterate_timeout(60, 'job started'):
            if len(self.builds):
                break
        self.waitUntilSettled()

        build = self.getJobFromHistory('python27-failure')
        self.assertEqual('FAILURE', build.result)
        cleanup_flag = os.path.join(self.jobdir_root, build.uuid +
                                    '.cleanup.flag')
        self.assertTrue(os.path.exists(cleanup_flag))
        with open(cleanup_flag) as f:
            self.assertEqual('False', f.readline())

    def test_cleanup_playbook_abort(self):
        # Test that when we abort a job the cleanup run is performed
        self.executor_server.verbose = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        for _ in iterate_timeout(60, 'job started'):
            if len(self.builds):
                break
        build = self.builds[0]

        post_start = os.path.join(self.jobdir_root, build.uuid +
                                  '.post_start.flag')
        for _ in iterate_timeout(60, 'job post running'):
            if os.path.exists(post_start):
                break
        # The post playbook has started, abort the job
        self.fake_gerrit.addEvent(A.getChangeAbandonedEvent())
        self.waitUntilSettled()

        build = self.getJobFromHistory('python27')
        self.assertEqual('ABORTED', build.result)

        post_end = os.path.join(self.jobdir_root, build.uuid +
                                '.post_end.flag')
        cleanup_flag = os.path.join(self.jobdir_root, build.uuid +
                                    '.cleanup.flag')
        self.assertTrue(os.path.exists(cleanup_flag))
        self.assertTrue(os.path.exists(post_start))
        self.assertFalse(os.path.exists(post_end))


class TestDataReturn(AnsibleZuulTestCase):
    tenant_config_file = 'config/data-return/main.yaml'

    def test_data_return(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='data-return', result='SUCCESS', changes='1,1'),
            dict(name='data-return-relative', result='SUCCESS', changes='1,1'),
            dict(name='child', result='SUCCESS', changes='1,1'),
        ], ordered=False)
        self.assertIn('- data-return http://example.com/test/log/url/',
                      A.messages[-1])
        self.assertIn('- data-return-relative '
                      'http://example.com/test/log/url/docs/index.html',
                      A.messages[-1])

    def test_data_return_child_jobs(self):
        self.wait_timeout = 120
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.release('data-return-child-jobs')
        self.waitUntilSettled()

        self.executor_server.release('data-return-child-jobs')
        self.waitUntilSettled()

        # Make sure skipped jobs are not reported as failing
        tenant = self.sched.abide.tenants.get("tenant-one")
        status = tenant.layout.pipelines["check"].formatStatusJSON()
        self.assertEqual(
            status["change_queues"][0]["heads"][0][0]["failing_reasons"], [])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='data-return-child-jobs', result='SUCCESS',
                 changes='1,1'),
            dict(name='data-return', result='SUCCESS', changes='1,1'),
        ])
        self.assertIn(
            '- data-return-child-jobs http://example.com/test/log/url/',
            A.messages[-1])
        self.assertIn(
            '- data-return http://example.com/test/log/url/',
            A.messages[-1])
        self.assertIn('child : SKIPPED', A.messages[-1])
        self.assertIn('Build succeeded', A.messages[-1])

    def test_data_return_invalid_child_job(self):
        A = self.fake_gerrit.addFakeChange('org/project2', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='data-return-invalid-child-job', result='SUCCESS',
                 changes='1,1')])
        self.assertIn(
            '- data-return-invalid-child-job http://example.com/test/log/url/',
            A.messages[-1])
        self.assertIn('data-return : SKIPPED', A.messages[-1])
        self.assertIn('Build succeeded', A.messages[-1])

    def test_data_return_skip_all_child_jobs(self):
        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='data-return-skip-all', result='SUCCESS',
                 changes='1,1'),
        ])
        self.assertIn(
            '- data-return-skip-all http://example.com/test/log/url/',
            A.messages[-1])
        self.assertIn('child : SKIPPED', A.messages[-1])
        self.assertIn('data-return : SKIPPED', A.messages[-1])
        self.assertIn('Build succeeded', A.messages[-1])

    def test_data_return_skip_all_child_jobs_with_soft_dependencies(self):
        A = self.fake_gerrit.addFakeChange('org/project-soft', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='data-return-cd', result='SUCCESS', changes='1,1'),
            dict(name='data-return-c', result='SUCCESS', changes='1,1'),
            dict(name='data-return-d', result='SUCCESS', changes='1,1'),
        ])
        self.assertIn('- data-return-cd http://example.com/test/log/url/',
                      A.messages[-1])
        self.assertIn('data-return-a : SKIPPED', A.messages[-1])
        self.assertIn('data-return-b : SKIPPED', A.messages[-1])
        self.assertIn('Build succeeded', A.messages[-1])

    def test_several_zuul_return(self):
        A = self.fake_gerrit.addFakeChange('org/project4', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='several-zuul-return-child', result='SUCCESS',
                 changes='1,1'),
        ])
        self.assertIn(
            '- several-zuul-return-child http://example.com/test/log/url/',
            A.messages[-1])
        self.assertIn('data-return : SKIPPED', A.messages[-1])
        self.assertIn('Build succeeded', A.messages[-1])

    def test_data_return_child_jobs_failure(self):
        A = self.fake_gerrit.addFakeChange('org/project5', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='data-return-child-jobs-failure',
                 result='FAILURE', changes='1,1'),
        ])

    def test_data_return_child_from_paused_job(self):
        A = self.fake_gerrit.addFakeChange('org/project6', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='data-return', result='SUCCESS', changes='1,1'),
            dict(name='paused-data-return-child-jobs',
                 result='SUCCESS', changes='1,1'),
        ])


class TestDiskAccounting(AnsibleZuulTestCase):
    config_file = 'zuul-disk-accounting.conf'
    tenant_config_file = 'config/disk-accountant/main.yaml'

    def test_disk_accountant_kills_job(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='dd-big-empty-file', result='ABORTED', changes='1,1')])


class TestMaxNodesPerJob(AnsibleZuulTestCase):
    tenant_config_file = 'config/multi-tenant/main.yaml'

    def test_max_timeout_exceeded(self):
        in_repo_conf = textwrap.dedent(
            """
            - job:
                name: test-job
                nodeset:
                  nodes:
                    - name: node01
                      label: fake
                    - name: node02
                      label: fake
                    - name: node03
                      label: fake
                    - name: node04
                      label: fake
                    - name: node05
                      label: fake
                    - name: node06
                      label: fake
            """)
        file_dict = {'.zuul.yaml': in_repo_conf}
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertIn('The job "test-job" exceeds tenant max-nodes-per-job 5.',
                      A.messages[0], "A should fail because of nodes limit")

        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertNotIn("exceeds tenant max-nodes", B.messages[0],
                         "B should not fail because of nodes limit")


class TestAllowedConnection(AnsibleZuulTestCase):
    config_file = 'zuul-connections-gerrit-and-github.conf'
    tenant_config_file = 'config/multi-tenant/main.yaml'

    def test_allowed_triggers(self):
        in_repo_conf = textwrap.dedent(
            """
            - pipeline:
                name: test
                manager: independent
                trigger:
                  github:
                    - event: pull_request
            """)
        file_dict = {'zuul.d/test.yaml': in_repo_conf}
        A = self.fake_gerrit.addFakeChange(
            'tenant-two-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertIn(
            'Unknown connection named "github"', A.messages[0],
            "A should fail because of allowed-trigger")

        B = self.fake_gerrit.addFakeChange(
            'tenant-one-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertNotIn(
            'Unknown connection named "github"', B.messages[0],
            "B should not fail because of allowed-trigger")

    def test_allowed_reporters(self):
        in_repo_conf = textwrap.dedent(
            """
            - pipeline:
                name: test
                manager: independent
                success:
                  outgoing_smtp:
                    to: you@example.com
            """)
        file_dict = {'zuul.d/test.yaml': in_repo_conf}
        A = self.fake_gerrit.addFakeChange(
            'tenant-one-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertIn(
            'Unknown connection named "outgoing_smtp"', A.messages[0],
            "A should fail because of allowed-reporters")

        B = self.fake_gerrit.addFakeChange(
            'tenant-two-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertNotIn(
            'Unknown connection named "outgoing_smtp"', B.messages[0],
            "B should not fail because of allowed-reporters")


class TestAllowedLabels(AnsibleZuulTestCase):
    config_file = 'zuul-connections-gerrit-and-github.conf'
    tenant_config_file = 'config/multi-tenant/main.yaml'

    def test_allowed_labels(self):
        in_repo_conf = textwrap.dedent(
            """
            - job:
                name: test
                nodeset:
                  nodes:
                    - name: controller
                      label: tenant-two-label
            """)
        file_dict = {'zuul.d/test.yaml': in_repo_conf}
        A = self.fake_gerrit.addFakeChange(
            'tenant-one-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertIn(
            'Label named "tenant-two-label" is not part of the allowed',
            A.messages[0],
            "A should fail because of allowed-labels")

    def test_disallowed_labels(self):
        in_repo_conf = textwrap.dedent(
            """
            - job:
                name: test
                nodeset:
                  nodes:
                    - name: controller
                      label: tenant-one-label
            """)
        file_dict = {'zuul.d/test.yaml': in_repo_conf}
        A = self.fake_gerrit.addFakeChange(
            'tenant-two-config', 'master', 'A', files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertIn(
            'Label named "tenant-one-label" is not part of the allowed',
            A.messages[0],
            "A should fail because of disallowed-labels")


class TestSecretLeaks(AnsibleZuulTestCase):
    tenant_config_file = 'config/secret-leaks/main.yaml'

    def searchForContent(self, path, content):
        matches = []
        for (dirpath, dirnames, filenames) in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                with open(filepath, 'rb') as f:
                    if content in f.read():
                        matches.append(filepath[len(path):])
        return matches

    def _test_secret_file(self):
        # Or rather -- test that they *don't* leak.
        # Keep the jobdir around so we can inspect contents.
        self.executor_server.keep_jobdir = True
        conf = textwrap.dedent(
            """
            - project:
                name: org/project
                check:
                  jobs:
                    - secret-file
            """)

        file_dict = {'.zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='secret-file', result='SUCCESS', changes='1,1'),
        ], ordered=False)
        matches = self.searchForContent(self.history[0].jobdir.root,
                                        b'test-password')
        self.assertEqual(set(['/work/secret-file.txt']),
                         set(matches))

    def test_secret_file(self):
        self._test_secret_file()

    def test_secret_file_verbose(self):
        # Output extra ansible info to exercise alternate logging code
        # paths.
        self.executor_server.verbose = True
        self._test_secret_file()

    def _test_secret_file_fail(self):
        # Or rather -- test that they *don't* leak.
        # Keep the jobdir around so we can inspect contents.
        self.executor_server.keep_jobdir = True
        conf = textwrap.dedent(
            """
            - project:
                name: org/project
                check:
                  jobs:
                    - secret-file-fail
            """)

        file_dict = {'.zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='secret-file-fail', result='FAILURE', changes='1,1'),
        ], ordered=False)
        matches = self.searchForContent(self.history[0].jobdir.root,
                                        b'test-password')
        self.assertEqual(set(['/work/failure-file.txt']),
                         set(matches))

    def test_secret_file_fail(self):
        self._test_secret_file_fail()

    def test_secret_file_fail_verbose(self):
        # Output extra ansible info to exercise alternate logging code
        # paths.
        self.executor_server.verbose = True
        self._test_secret_file_fail()


class TestJobOutput(AnsibleZuulTestCase):
    tenant_config_file = 'config/job-output/main.yaml'

    def _get_file(self, build, path):
        p = os.path.join(build.jobdir.root, path)
        with open(p) as f:
            return f.read()

    def test_job_output(self):
        # Verify that command standard output appears in the job output,
        # and that failures in the final playbook get logged.

        # This currently only verifies we receive output from
        # localhost.  Notably, it does not verify we receive output
        # via zuul_console streaming.
        self.executor_server.keep_jobdir = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='job-output', result='SUCCESS', changes='1,1'),
        ], ordered=False)

        token = 'Standard output test %s' % (self.history[0].jobdir.src_root)
        j = json.loads(self._get_file(self.history[0],
                                      'work/logs/job-output.json'))
        self.assertEqual(token,
                         j[0]['plays'][0]['tasks'][1]
                         ['hosts']['test_node']['stdout'])
        self.assertTrue(j[0]['plays'][0]['tasks'][2]
                        ['hosts']['test_node']['skipped'])
        self.assertTrue(j[0]['plays'][0]['tasks'][3]
                        ['hosts']['test_node']['failed'])
        self.assertEqual(
            "This is a handler",
            j[0]['plays'][0]['tasks'][4]
            ['hosts']['test_node']['stdout'])

        self.log.info(self._get_file(self.history[0],
                                     'work/logs/job-output.txt'))
        self.assertIn(token,
                      self._get_file(self.history[0],
                                     'work/logs/job-output.txt'))

    def test_job_output_missing_role(self):
        # Verify that ansible errors such as missing roles are part of the
        # buildlog.

        self.executor_server.keep_jobdir = True
        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='job-output-missing-role', result='FAILURE',
                 changes='1,1'),
            dict(name='job-output-missing-role-include', result='FAILURE',
                 changes='1,1'),
        ], ordered=False)

        for history in self.history:
            job_output = self._get_file(history,
                                        'work/logs/job-output.txt')
            self.assertIn('the role \'not_existing\' was not found',
                          job_output)

    def test_job_output_failure_log(self):
        logger = logging.getLogger('zuul.AnsibleJob')
        output = io.StringIO()
        logger.addHandler(logging.StreamHandler(output))

        # Verify that a failure in the last post playbook emits the contents
        # of the json output to the log
        self.executor_server.keep_jobdir = True
        A = self.fake_gerrit.addFakeChange('org/project2', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='job-output-failure',
                 result='POST_FAILURE', changes='1,1'),
        ], ordered=False)

        token = 'Standard output test %s' % (self.history[0].jobdir.src_root)
        j = json.loads(self._get_file(self.history[0],
                                      'work/logs/job-output.json'))
        self.assertEqual(token,
                         j[0]['plays'][0]['tasks'][1]
                         ['hosts']['test_node']['stdout'])

        self.log.info(self._get_file(self.history[0],
                                     'work/logs/job-output.json'))
        self.assertIn(token,
                      self._get_file(self.history[0],
                                     'work/logs/job-output.txt'))

        log_output = output.getvalue()
        self.assertIn('Final playbook failed', log_output)
        self.assertIn('Failure test', log_output)


class TestPlugins(AnsibleZuulTestCase):
    tenant_config_file = 'config/speculative-plugins/main.yaml'

    def _run_job(self, job_name, project='org/project', roles=''):
        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        conf = textwrap.dedent(
            """
            - job:
                name: {job_name}
                run: playbooks/{job_name}/test.yaml
                nodeset:
                  nodes:
                    - name: controller
                      label: whatever
                {roles}
            - project:
                check:
                  jobs:
                    - {job_name}
            """.format(job_name=job_name, roles=roles))

        file_dict = {'zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange(project, 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        return A

    def _check_job(self, job_name, project='org/project', roles=''):
        A = self._run_job(job_name, project, roles)

        message = A.messages[0]
        self.assertIn('ERROR Ansible plugin dir', message)
        self.assertIn('found adjacent to playbook', message)
        self.assertIn('in non-trusted repo', message)

    def test_filter_plugin(self):
        self._check_job('filter-plugin-playbook')
        self._check_job('filter-plugin-playbook-symlink')
        self._check_job('filter-plugin-bare-role')
        self._check_job('filter-plugin-role')
        self._check_job('filter-plugin-repo-role', project='org/projectrole',
                        roles="roles: [{zuul: 'org/projectrole'}]")
        self._check_job('filter-plugin-shared-role',
                        roles="roles: [{zuul: 'org/project2'}]")
        self._check_job(
            'filter-plugin-shared-bare-role',
            roles="roles: [{zuul: 'org/project3', name: 'shared'}]")

    def test_implicit_role_not_added(self):
        # This fails because the job uses the role which isn't added
        # to the role path, but it's a normal ansible failure, not a
        # Zuul executor error.
        A = self._run_job('filter-plugin-repo-role', project='org/projectrole')
        self.assertHistory([
            dict(name='filter-plugin-repo-role', result='FAILURE',
                 changes='1,1'),
        ], ordered=False)
        message = A.messages[0]
        self.assertNotIn('Ansible plugin', message)


class TestNoLog(AnsibleZuulTestCase):
    tenant_config_file = 'config/ansible-no-log/main.yaml'

    def _get_file(self, build, path):
        p = os.path.join(build.jobdir.root, path)
        with open(p) as f:
            return f.read()

    def test_no_log_unreachable(self):
        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        json_log = self._get_file(self.history[0], 'work/logs/job-output.json')
        text_log = self._get_file(self.history[0], 'work/logs/job-output.txt')

        self.assertNotIn('my-very-secret-password-1', json_log)
        self.assertNotIn('my-very-secret-password-2', json_log)
        self.assertNotIn('my-very-secret-password-1', text_log)
        self.assertNotIn('my-very-secret-password-2', text_log)


class TestUnreachable(AnsibleZuulTestCase):
    tenant_config_file = 'config/ansible-unreachable/main.yaml'

    def _get_file(self, build, path):
        p = os.path.join(build.jobdir.root, path)
        with open(p) as f:
            return f.read()

    def test_unreachable(self):
        self.wait_timeout = 120

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # The result must be retry limit because jobs with unreachable nodes
        # will be retried.
        self.assertIn('RETRY_LIMIT', A.messages[0])
        self.assertHistory([
            dict(name='pre-unreachable', result=None, changes='1,1'),
            dict(name='pre-unreachable', result=None, changes='1,1'),
            dict(name='run-unreachable', result=None, changes='1,1'),
            dict(name='run-unreachable', result=None, changes='1,1'),
            dict(name='post-unreachable', result=None, changes='1,1'),
            dict(name='post-unreachable', result=None, changes='1,1'),
        ], ordered=False)
        unreachable_log = self._get_file(self.history[0],
                                         '.ansible/nodes.unreachable')
        self.assertEqual('fake\n', unreachable_log)


class TestJobPause(AnsibleZuulTestCase):
    tenant_config_file = 'config/job-pause/main.yaml'

    def _get_file(self, build, path):
        p = os.path.join(build.jobdir.root, path)
        with open(p) as f:
            return f.read()

    def test_job_pause(self):
        """
        compile1
        +--> compile2
        |    +--> test-after-compile2
        +--> test1-after-compile1
        +--> test2-after-compile1
        test-good
        test-fail
        """

        self.wait_timeout = 120

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for _ in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='test-fail', result='FAILURE', changes='1,1'),
            dict(name='test-good', result='SUCCESS', changes='1,1'),
            dict(name='test1-after-compile1', result='SUCCESS', changes='1,1'),
            dict(name='test2-after-compile1', result='SUCCESS', changes='1,1'),
            dict(name='test-after-compile2', result='SUCCESS', changes='1,1'),
            dict(name='compile2', result='SUCCESS', changes='1,1'),
            dict(name='compile1', result='SUCCESS', changes='1,1'),
        ], ordered=False)

        # The order of some of these tests is not deterministic so check that
        # the last two are compile2, compile1 in this order.
        history_compile1 = self.history[-1]
        history_compile2 = self.history[-2]
        self.assertEqual('compile1', history_compile1.name)
        self.assertEqual('compile2', history_compile2.name)

    def test_job_pause_retry(self):
        """
        Tests that a paused job that gets lost due to an executor restart is
        retried together with all child jobs.

        This test will wait until compile1 is paused and then fails it. The
        expectation is that all child jobs are retried even if they already
        were successful.

        compile1 --+
                   +--> test1-after-compile1
                   +--> test2-after-compile1
                   +--> compile2 --+
                                   +--> test-after-compile2
        test-good
        test-fail
        """
        self.wait_timeout = 120

        self.executor_server.hold_jobs_in_build = True

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled("patchset uploaded")

        self.executor_server.release('test-.*')
        self.executor_server.release('compile1')
        self.waitUntilSettled("released compile1")

        # test-fail and test-good must be finished by now
        self.assertHistory([
            dict(name='test-fail', result='FAILURE', changes='1,1'),
            dict(name='test-good', result='SUCCESS', changes='1,1'),
        ], ordered=False)

        # Further compile1 must be in paused state and its three children in
        # the queue. waitUltilSettled can return either directly after the job
        # pause or after the child jobs are enqueued. So to make this
        # deterministic we wait for the child jobs here
        for _ in iterate_timeout(60, 'waiting for child jobs'):
            if len(self.builds) == 4:
                break
        self.waitUntilSettled("child jobs are running")

        compile1 = self.builds[0]
        self.assertTrue(compile1.paused)

        # Now resume resume the compile2 sub tree so we can later check if all
        # children restarted
        self.executor_server.release('compile2')
        for _ in iterate_timeout(60, 'waiting for child jobs'):
            if len(self.builds) == 5:
                break
        self.waitUntilSettled("release compile2")
        self.executor_server.release('test-after-compile2')
        self.waitUntilSettled("release test-after-compile2")
        self.executor_server.release('compile2')
        self.waitUntilSettled("release compile2 again")
        self.assertHistory([
            dict(name='test-fail', result='FAILURE', changes='1,1'),
            dict(name='test-good', result='SUCCESS', changes='1,1'),
            dict(name='compile2', result='SUCCESS', changes='1,1'),
            dict(name='test-after-compile2', result='SUCCESS', changes='1,1'),
        ], ordered=False)

        # Stop the job worker of compile1 to simulate an executor restart
        for job_worker in self.executor_server.job_workers.values():
            if job_worker.job.unique == compile1.unique:
                job_worker.stop()
        self.waitUntilSettled("Stop job")

        # Only compile1 must be waiting
        for _ in iterate_timeout(60, 'waiting for compile1 job'):
            if len(self.builds) == 1:
                break
        self.waitUntilSettled("only compile1 is running")
        self.assertBuilds([dict(name='compile1', changes='1,1')])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled("global release")

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for x in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='test-fail', result='FAILURE', changes='1,1'),
            dict(name='test-good', result='SUCCESS', changes='1,1'),
            dict(name='compile2', result='SUCCESS', changes='1,1'),
            dict(name='compile2', result='SUCCESS', changes='1,1'),
            dict(name='test-after-compile2', result='SUCCESS', changes='1,1'),
            dict(name='test-after-compile2', result='SUCCESS', changes='1,1'),
            dict(name='compile1', result='ABORTED', changes='1,1'),
            dict(name='compile1', result='SUCCESS', changes='1,1'),
            dict(name='test1-after-compile1', result='ABORTED', changes='1,1'),
            dict(name='test2-after-compile1', result='ABORTED', changes='1,1'),
            dict(name='test1-after-compile1', result='SUCCESS', changes='1,1'),
            dict(name='test2-after-compile1', result='SUCCESS', changes='1,1'),
        ], ordered=False)

    def test_job_node_failure_resume(self):
        self.wait_timeout = 120

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True

        # Second node request should fail
        fail = {'_oid': '199-0000000001'}
        self.fake_nodepool.addFailRequest(fail)

        A = self.fake_gerrit.addFakeChange('org/project2', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for x in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertEqual([], self.builds)
        self.assertHistory([
            dict(name='just-pause', result='SUCCESS', changes='1,1'),
        ], ordered=False)

    def test_job_pause_skipped_child(self):
        """
        Tests that a paused job is resumed with externally skipped jobs.

        Tests that this situation won't lead to stuck buildsets.
        Compile pauses before pre-test fails.

        1. compile (pauses) --+
                              |
                              +--> test (skipped because of pre-test)
                              |
        2. pre-test (fails) --+
        """
        self.wait_timeout = 120
        self.executor_server.hold_jobs_in_build = True

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.release('compile')
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='pre-test', result='FAILURE', changes='1,1'),
            dict(name='compile', result='SUCCESS', changes='1,1'),
        ])

        self.assertIn('test : SKIPPED', A.messages[0])

    def test_job_pause_pre_skipped_child(self):
        """
        Tests that a paused job is resumed with pre-existing skipped jobs.

        Tests that this situation won't lead to stuck buildsets.
        The pre-test fails before compile pauses so test is already skipped
        when compile pauses.

        1. pre-test (fails) --+
                              |
                              +--> test (skipped because of pre-test)
                              |
        2. compile (pauses) --+
        """
        self.wait_timeout = 120
        self.executor_server.hold_jobs_in_build = True

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        self.executor_server.keep_jobdir = True

        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.release('pre-test')
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for x in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='pre-test', result='FAILURE', changes='1,1'),
            dict(name='compile', result='SUCCESS', changes='1,1'),
        ])

        self.assertIn('test : SKIPPED', A.messages[0])


class TestJobPausePostFail(AnsibleZuulTestCase):
    tenant_config_file = 'config/job-pause2/main.yaml'

    def _get_file(self, build, path):
        p = os.path.join(build.jobdir.root, path)
        with open(p) as f:
            return f.read()

    def test_job_pause_post_fail(self):
        """Tests that a parent job which has a post failure does not
        retroactively set its child job's result to SKIPPED.

        compile
        +--> test

        """
        # Output extra ansible info so we might see errors.
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for x in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='test', result='SUCCESS', changes='1,1'),
            dict(name='compile', result='POST_FAILURE', changes='1,1'),
        ])


class TestContainerJobs(AnsibleZuulTestCase):
    tenant_config_file = "config/container-build-resources/main.yaml"

    def test_container_jobs(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='container-machine', result='SUCCESS', changes='1,1'),
            dict(name='container-native', result='SUCCESS', changes='1,1'),
        ], ordered=False)


class TestProvidesRequiresPause(AnsibleZuulTestCase):
    tenant_config_file = "config/provides-requires-pause/main.yaml"

    def test_provides_requires_pause(self):
        # Changes share a queue, with both running at the same time.
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        # Release image-build, it should cause both instances of
        # image-user to run.
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for _ in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='image-builder', result='SUCCESS', changes='1,1'),
            dict(name='image-user', result='SUCCESS', changes='1,1'),
            dict(name='image-user', result='SUCCESS', changes='1,1 2,1'),
        ], ordered=False)
        build = self.getJobFromHistory('image-user', project='org/project2')
        self.assertEqual(
            build.parameters['zuul']['artifacts'],
            [{
                'project': 'org/project1',
                'change': '1',
                'patchset': '1',
                'job': 'image-builder',
                'url': 'http://example.com/image',
                'name': 'image',
            }])


class TestJobPausePriority(AnsibleZuulTestCase):
    tenant_config_file = 'config/job-pause-priority/main.yaml'

    def test_paused_job_priority(self):
        "Test that nodes for children of paused jobs have a higher priority"

        self.fake_nodepool.pause()
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        reqs = self.fake_nodepool.getNodeRequests()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]['_oid'], '100-0000000000')
        self.assertEqual(reqs[0]['provider'], None)

        self.fake_nodepool.unpause()
        self.waitUntilSettled()
        self.fake_nodepool.pause()
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()

        for x in iterate_timeout(60, 'paused job'):
            reqs = self.fake_nodepool.getNodeRequests()
            if reqs:
                break

        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]['_oid'], '099-0000000001')
        self.assertEqual(reqs[0]['provider'], 'test-provider')

        self.fake_nodepool.unpause()
        self.waitUntilSettled()


class TestAnsibleVersion(AnsibleZuulTestCase):
    tenant_config_file = 'config/ansible-versions/main.yaml'

    def test_ansible_versions(self):
        """
        Tests that jobs run with the requested ansible version.
        """
        A = self.fake_gerrit.addFakeChange('common-config', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='ansible-default', result='SUCCESS', changes='1,1'),
            dict(name='ansible-26', result='SUCCESS', changes='1,1'),
            dict(name='ansible-27', result='SUCCESS', changes='1,1'),
            dict(name='ansible-28', result='SUCCESS', changes='1,1'),
            dict(name='ansible-29', result='SUCCESS', changes='1,1'),
        ], ordered=False)


class TestDefaultAnsibleVersion(AnsibleZuulTestCase):
    config_file = 'zuul-default-ansible-version.conf'
    tenant_config_file = 'config/ansible-versions/main.yaml'

    def test_ansible_versions(self):
        """
        Tests that jobs run with the requested ansible version.
        """
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='ansible-default-zuul-conf', result='SUCCESS',
                 changes='1,1'),
            dict(name='ansible-26', result='SUCCESS', changes='1,1'),
            dict(name='ansible-27', result='SUCCESS', changes='1,1'),
            dict(name='ansible-28', result='SUCCESS', changes='1,1'),
            dict(name='ansible-29', result='SUCCESS', changes='1,1'),
        ], ordered=False)
