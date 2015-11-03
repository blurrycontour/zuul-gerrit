# Copyright 2015 GoodData
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

import logging
import re
from testtools.matchers import MatchesRegex
from tests.base import ZuulTestCase, random_sha1

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestGithubDriver(ZuulTestCase):
    config_file = 'zuul-github-driver.conf'
    tenant_config_file = 'config/github-driver/main.yaml'

    def setup_config(self):
        super(TestGithubDriver, self).setup_config()

    def test_pull_event(self):
        self.executor_server.hold_jobs_in_build = True

        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        build_params = self.builds[0].parameters
        self.assertEqual('master', build_params['ZUUL_BRANCH'])
        self.assertEqual(str(pr.number), build_params['ZUUL_CHANGE'])
        self.assertEqual(pr.head_sha, build_params['ZUUL_PATCHSET'])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['vars']['zuul']
        self.assertEqual(pr.number, zuulvars['change'])
        self.assertEqual(pr.head_sha, zuulvars['patchset'])
        self.assertEqual(1, len(pr.comments))

    def test_comment_event(self):
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getCommentAddedEvent('test me'))
        self.waitUntilSettled()
        self.assertEqual(2, len(self.history))

    def test_comment_unmatched_event(self):
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getCommentAddedEvent('casual comment'))
        self.waitUntilSettled()
        self.assertEqual(0, len(self.history))

    def test_tag_event(self):
        self.executor_server.hold_jobs_in_build = True

        sha = random_sha1()
        self.fake_github.emitEvent(
            self.fake_github.getTagEvent('org/project', 'newtag', sha))
        self.waitUntilSettled()

        build_params = self.builds[0].parameters
        self.assertEqual('refs/tags/newtag', build_params['ZUUL_REF'])
        self.assertEqual('00000000000000000000000000000000',
                         build_params['ZUUL_OLDREV'])
        self.assertEqual(sha, build_params['ZUUL_NEWREV'])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-tag').result)

    def test_push_event(self):
        self.executor_server.hold_jobs_in_build = True

        old_sha = random_sha1()
        new_sha = random_sha1()
        self.fake_github.emitEvent(
            self.fake_github.getPushEvent('org/project', 'master',
                                          old_sha, new_sha))
        self.waitUntilSettled()

        build_params = self.builds[0].parameters
        self.assertEqual('refs/heads/master', build_params['ZUUL_REF'])
        self.assertEqual(old_sha, build_params['ZUUL_OLDREV'])
        self.assertEqual(new_sha, build_params['ZUUL_NEWREV'])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-post').result)

    def test_git_https_url(self):
        """Test that git_ssh option gives git url with ssh"""
        url = self.fake_github.real_getGitUrl('org/project')
        self.assertEqual('https://github.com/org/project', url)

    def test_git_ssh_url(self):
        """Test that git_ssh option gives git url with ssh"""
        url = self.fake_github_ssh.real_getGitUrl('org/project')
        self.assertEqual('ssh://git@github.com/org/project.git', url)

    def test_report_pull_status(self):
        # pipeline reports pull status both on start and success
        self.executor_server.hold_jobs_in_build = True
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertIn('check', pr.statuses)
        check_status = pr.statuses['check']
        self.assertEqual('Standard check', check_status['description'])
        self.assertEqual('pending', check_status['state'])
        self.assertEqual('http://zuul.example.com/status', check_status['url'])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        check_status = pr.statuses['check']
        self.assertEqual('Standard check', check_status['description'])
        self.assertEqual('success', check_status['state'])
        self.assertEqual('', check_status['url'])

        # pipeline does not report any status
        self.executor_server.hold_jobs_in_build = True
        self.fake_github.emitEvent(
            pr.getCommentAddedEvent('reporting check'))
        self.waitUntilSettled()
        self.assertNotIn('reporting', pr.statuses)
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertNotIn('reporting', pr.statuses)

    def test_report_pull_comment(self):
        # pipeline reports comment on success
        self.executor_server.hold_jobs_in_build = True
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getPullRequestOpenedEvent())
        self.waitUntilSettled()
        self.assertEqual(0, len(pr.comments))

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(1, len(pr.comments))
        self.assertThat(pr.comments[0],
                        MatchesRegex('.*Build succeeded.*', re.DOTALL))

        # pipeline reports comment on start
        self.executor_server.hold_jobs_in_build = True
        self.fake_github.emitEvent(
            pr.getCommentAddedEvent('reporting check'))
        self.waitUntilSettled()
        self.assertEqual(2, len(pr.comments))
        self.assertThat(pr.comments[1],
                        MatchesRegex('.*Starting reporting jobs.*', re.DOTALL))
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(2, len(pr.comments))

    def test_report_pull_merge(self):
        # pipeline merges the pull request on success
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getCommentAddedEvent('merge me'))
        self.waitUntilSettled()
        self.assertTrue(pr.is_merged)

    def test_report_pull_merge_failure(self):
        # pipeline merges the pull request on success
        self.fake_github.merge_failure = True
        pr = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(pr.getCommentAddedEvent('merge me'))
        self.waitUntilSettled()
        self.assertFalse(pr.is_merged)
        self.fake_github.merge_failure = False

    def test_report_pull_merge_not_allowed_once(self):
        # pipeline merges the pull request on second run of merge
        # first merge failed on 405 Method Not Allowed error
        self.fake_github.merge_not_allowed_count = 1
        A = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(A.getCommentAddedEvent('merge me'))
        self.waitUntilSettled()
        self.assertTrue(A.is_merged)

    def test_report_pull_merge_not_allowed_twice(self):
        # pipeline does not merge the pull request
        # merge failed on 405 Method Not Allowed error - twice
        self.fake_github.merge_not_allowed_count = 2
        A = self.fake_github.openFakePullRequest('org/project', 'master')
        self.fake_github.emitEvent(A.getCommentAddedEvent('merge me'))
        self.waitUntilSettled()
        self.assertFalse(A.is_merged)
