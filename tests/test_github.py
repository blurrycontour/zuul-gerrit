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
        def assertTestJobsParams():
            self.waitUntilSettled()
            build = self.builds[0]
            self.assertEqual(build.name, 'project-test1')
            self.assertEqual(build.parameters['ZUUL_PROJECT'],
                             'github/project')
            self.assertEqual(build.parameters['ZUUL_PIPELINE'], 'check')
            self.assertEqual(build.parameters['ZUUL_REF'],
                             'refs/pull/%s/head' % pull_request.number)
            self.assertEqual(build.parameters['ZUUL_OLDREV'],
                             pull_request.getBaseBranchSha())
            self.assertEqual(build.parameters['ZUUL_NEWREV'],
                             pull_request.getPRHeadSha())
            self.worker.release('project-test1')
            self.waitUntilSettled()

        self.worker.hold_jobs_in_build = True

        # open PR
        pull_request = self.fake_github.openFakePullRequest('github/project',
                                                            'master')
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 1)

        # push to PR
        pull_request.addCommit()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 2)

        # force-push to PR
        pull_request.forcePush()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 3)

        # close the PR
        pull_request.close()
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 0)
        self.worker.release()
        self.waitUntilSettled()
        self.assertEqual(len(pull_request.comments), 3)

        # reopen the PR
        pull_request.reopen()
        assertTestJobsParams()
        self.assertEqual(len(pull_request.comments), 4)

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
        self.assertEqual(len(pull_request.comments), 4)

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
