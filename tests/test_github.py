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

from tests.base import ZuulTestCase

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestGithub(ZuulTestCase):

    def setup_config(self, config_file='zuul-github.conf'):
        super(TestGithub, self).setup_config(config_file)

    def test_pr_scenario(self):
        """Standard work flow for a GitHub pull request
        * open a PR from a source branch
        * add some more commits to the source branch
        * force push to the source branch
        * close the PR
        * reopen the PR
        * merge the PR
        """
        self.worker.registerFunction('set_description:' +
                                     self.worker.worker_id)

        def assertTestJobsParams():
            self.waitUntilSettled()
            build = self.builds[0]
            self.assertEqual(build.name, 'project-test1')
            self.assertThat(build.parameters['ZUUL_REF'],
                            MatchesRegex('^refs/zuul/master/.*$'))
            self.assertEqual(build.parameters['ZUUL_COMMIT'],
                             pull_request.getPRHeadSha())
            self.assertEqual(build.parameters['ZUUL_PROJECT'],
                             'github/project')
            self.assertEqual(build.parameters['ZUUL_PIPELINE'], 'check')
            self.assertEqual(build.parameters['ZUUL_BRANCH'], 'master')
            self.assertEqual(build.parameters['ZUUL_CHANGE'],
                             str(pull_request.number))
            self.worker.release('project-test1')
            self.waitUntilSettled()

        self.worker.hold_jobs_in_build = True

        # open PR
        pull_request = self.fake_github.openFakePullRequest('github/project',
                                                            'master')
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 1)
        descr = self.history[0].description
        self.assertThat(descr, MatchesRegex(
            r'.*<\s*a\s+href='
            '[\'"]https://github.com/github/project/pull/%s[\'"]'
            '\s*>%s<\s*/a\s*>' %
            (pull_request.number, pull_request.number),
            re.DOTALL
        ))

        # comment PR with a matching keyword
        pull_request.addComment('test me')
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 3)

        # comment PR without a matching keyword
        pull_request.addComment('just a plain comment')
        self.waitUntilSettled()
        self.assertEqual(len(pull_request.comments), 4)

        # push to PR
        pull_request.addCommit()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 5)

        # force-push to PR
        pull_request.forcePush()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 6)

        # close the PR
        pull_request.close()
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 0)
        self.worker.release()
        self.waitUntilSettled()
        self.assertEqual(len(pull_request.comments), 6)

        # reopen the PR
        pull_request.reopen()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 7)

        # merge the PR
        pull_request.merge()
        self.waitUntilSettled()
        build = self.builds[0]
        self.assertEqual(build.name, 'project-push')
        self.assertEqual(build.parameters['ZUUL_PROJECT'],
                         'github/project')
        self.assertEqual(build.parameters['ZUUL_PIPELINE'], 'post')
        self.assertEqual(build.parameters['ZUUL_REF'], 'refs/heads/master')
        self.assertEqual(build.parameters['ZUUL_NEWREV'],
                         pull_request.getBaseBranchSha())
        self.worker.release('project-push')
        self.waitUntilSettled()
        self.assertEqual(len(pull_request.comments), 7)

    def test_tag_scenario(self):
        """Tag a GitHub branch."""
        self.worker.hold_jobs_in_build = True

        self.fake_github.tagBranch('github/project', 'master', 'newtag')
        self.waitUntilSettled()
        build = self.builds[0]
        self.assertEqual(build.name, 'project-tag')
        self.assertEqual(build.parameters['ZUUL_REF'], 'refs/tags/newtag')

        self.worker.release()
        self.waitUntilSettled()

    def test_git_https_url(self):
        """Test that git_ssh option gives git url with ssh"""
        url = self.fake_github.real_getGitUrl('github/project')
        self.assertThat(url, MatchesRegex('https://github.com/github/project'))

    def test_git_ssh_url(self):
        """Test that git_ssh option gives git url with ssh"""
        url = self.fake_github_ssh.real_getGitUrl('github/project')
        self.assertThat(
            url,
            MatchesRegex('ssh://git@github.com:github/project.git'))
