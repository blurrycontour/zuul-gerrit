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


class TestGiteaCrossRepoDeps(ZuulTestCase):
    """Test Gitea cross-repo dependencies"""
    config_file = 'zuul-gitea-driver.conf'
    scheduler_count = 1

    @simple_layout('layouts/crd-gitea.yaml', driver='gitea')
    def test_crd_independent(self):
        "Test cross-repo dependences on an independent pipeline"

        # Create a change in project1 that a project2 change will depend on
        A = self.fake_gitea.openFakePullRequest('org/project1', 'master', 'A')

        # Create a commit in B that sets the dependency on A
        msg = (
            "Depends-On: "
            "https://fakegitea.com/org/project1/pulls/%s" % A.number
        )
        B = self.fake_gitea.openFakePullRequest(
            'org/project2', 'master', 'B', initial_comment=msg)

        # Make an event to re-use
        event = B.getPullRequestUpdatedEvent()

        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()

        # The changes for the job from project2 should include the project1
        # PR contet
        changes = self.getJobFromHistory(
            'project2-test', 'org/project2').changes

        self.assertEqual(
            changes,
            "%s,%s %s,%s" % (A.number, A.head_sha, B.number, B.head_sha)
        )

        # There should be no more changes in the queue
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        self.assertEqual(len(tenant.layout.pipelines['check'].queues), 0)

    @simple_layout('layouts/crd-gitea.yaml', driver='gitea')
    def test_crd_dependent(self):
        "Test cross-repo dependences on a dependent pipeline"

        # Create a change in project3 that a project4 change will depend on
        A = self.fake_gitea.openFakePullRequest('org/project3', 'master', 'A')

        # Create a commit in B that sets the dependency on A
        msg = (
            "Depends-On: "
            "https://fakegitea.com/org/project3/pulls/%s" % A.number
        )
        B = self.fake_gitea.openFakePullRequest(
            'org/project4', 'master', 'B', initial_comment=msg)

        A.addReview()
        B.addReview()
        # Make an event to re-use
        event = B.getPullRequestUpdatedEvent()

        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()

        # The changes for the job from project4 should include the project3
        # PR content
        changes = self.getJobFromHistory(
            'project4-test', 'org/project4').changes

        self.assertEqual(
            changes,
            "%s,%s %s,%s" % (A.number, A.head_sha, B.number, B.head_sha)
        )
        self.assertTrue(A.is_merged)
        self.assertTrue(B.is_merged)

    @simple_layout('layouts/crd-gitea.yaml', driver='gitea')
    def test_crd_dependent_merged(self):
        "Test cross-repo dependences on a dependent pipeline with merged dep"

        # Create a change in project3 that a project4 change will depend on
        A = self.fake_gitea.openFakePullRequest('org/project3', 'master', 'A')

        # Create a commit in B that sets the dependency on A
        msg = (
            "Depends-On: "
            "https://fakegitea.com/org/project3/pulls/%s" % A.number
        )
        B = self.fake_gitea.openFakePullRequest(
            'org/project4', 'master', 'B', initial_comment=msg)

        A.mergePullRequest()
        B.addReview()
        # Make an event to re-use
        event = B.getPullRequestUpdatedEvent()

        self.fake_gitea.emitEvent(event)
        self.waitUntilSettled()

        # The changes for the job from project4 should include the project3
        # PR content
        changes = self.getJobFromHistory(
            'project4-test', 'org/project4').changes

        self.assertEqual(changes, "%s,%s" % (B.number,
                                             B.head_sha))

        self.assertTrue(B.is_merged)
