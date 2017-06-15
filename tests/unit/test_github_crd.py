#!/usr/bin/env python
# Copyright (c) 2017 IBM Corp.
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

from tests.base import ZuulTestCase, simple_layout

class TestGithubCrossRepoDeps(ZuulTestCase):
    """Test Github cross-repo dependencies"""
    config_file = 'zuul-github-driver.conf'

    @simple_layout('layouts/crd-github.yaml', driver='github')
    def test_crd_independent(self):
        "Test cross-repo dependences on an independent pipeline"

        # Create a change in project1 that a project2 change will depend on
        A = self.fake_github.openFakePullRequest('org/project1', 'master', 'A')
        B = self.fake_github.openFakePullRequest('org/project2', 'master', 'A')

        # Create a commit in B that sets the dependency on A
        msg = "Depends-On: https://github.com/org/project1/pull/%s" % A.number
        B.addCommit(msg=msg)

        # Make an event to re-use
        sevent = B.getPullRequestSynchronizeEvent()

        self.fake_github.emitEvent(sevent)
        self.waitUntilSettled()

        # The changes for the job from project2 should include the project1
        # PR content
        changes = self.getJobFromHistory(
            'project2-test', 'org/project2').changes
        
        self.assertEqual(changes, "%s,%s %s,%s" % (A.number,
                                                   A.head_sha,
                                                   B.number,
                                                   B.head_sha))