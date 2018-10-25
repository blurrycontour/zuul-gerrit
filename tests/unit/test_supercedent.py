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

from tests.base import ZuulTestCase


class TestSupercedent(ZuulTestCase):
    config_file = 'zuul-connections-gerrit-and-github.conf'
    tenant_config_file = 'config/supercedent-multi-driver/main.yaml'

    def test_supercedent_gerrit(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        arev = A.patchsets[-1]['revision']
        A.setMerged()
        self.fake_gerrit.addEvent(A.getRefUpdatedEvent())
        self.waitUntilSettled()

        # We should never run jobs for more than one change at a time
        self.assertEqual(len(self.builds), 1)

        # This change should be superceded by the next
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')
        B.setMerged()
        self.fake_gerrit.addEvent(B.getRefUpdatedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        C = self.fake_gerrit.addFakeChange('org/project', 'master', 'C')
        crev = C.patchsets[-1]['revision']
        C.setMerged()
        self.fake_gerrit.addEvent(C.getRefUpdatedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        self.executor_server.hold_jobs_in_build = True
        self.orderedRelease()
        self.assertHistory([
            dict(name='post-job', result='SUCCESS', newrev=arev),
            dict(name='post-job', result='SUCCESS', newrev=crev),
        ], ordered=False)

    def test_supercedent_branches_gerrit(self):
        self.executor_server.hold_jobs_in_build = True
        self.create_branch('org/project', 'stable')
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        arev = A.patchsets[-1]['revision']
        A.setMerged()
        self.fake_gerrit.addEvent(A.getRefUpdatedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        # This change should not be superceded
        B = self.fake_gerrit.addFakeChange('org/project', 'stable', 'B')
        brev = B.patchsets[-1]['revision']
        B.setMerged()
        self.fake_gerrit.addEvent(B.getRefUpdatedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 2)

        self.executor_server.hold_jobs_in_build = True
        self.orderedRelease()
        self.assertHistory([
            dict(name='post-job', result='SUCCESS', newrev=arev),
            dict(name='post-job', result='SUCCESS', newrev=brev),
        ], ordered=False)

    def test_supercedent_github(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_github.openFakePullRequest('org/project1', 'master', 'A')
        aref = "refs/pull/{}".format(A.getPRReference())
        A.setMerged("Merge PR A")
        self.fake_github.emitEvent(A.getPullRequestClosedEvent())
        self.waitUntilSettled()

        # We should never run jobs for more than one change at a time
        self.assertEqual(len(self.builds), 1)

        # This change should be superceded by the next
        B = self.fake_github.openFakePullRequest('org/project1', 'master', 'B')
        B.setMerged("Merge PR B")
        self.fake_github.emitEvent(B.getPullRequestClosedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        C = self.fake_github.openFakePullRequest('org/project1', 'master', 'C')
        cref = "refs/pull/{}".format(C.getPRReference())
        C.setMerged("Merge PR C")
        self.fake_github.emitEvent(C.getPullRequestClosedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        self.executor_server.hold_jobs_in_build = True
        self.orderedRelease()
        self.assertHistory([
            dict(name='post-job', result='SUCCESS', ref=aref),
            dict(name='post-job', result='SUCCESS', ref=cref),
        ], ordered=False)

    def test_supercedent_branches_github(self):
        self.executor_server.hold_jobs_in_build = True
        self.create_branch('org/project1', 'stable')
        A = self.fake_github.openFakePullRequest('org/project1', 'master', 'A')
        aref = "refs/pull/{}".format(A.getPRReference())
        A.setMerged("Merge PR A")
        self.fake_github.emitEvent(A.getPullRequestClosedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        # This change should not be superceded
        B = self.fake_github.openFakePullRequest('org/project1', 'stable', 'B')
        bref = "refs/pull/{}".format(B.getPRReference())
        B.setMerged("Merge PR B")
        self.fake_github.emitEvent(B.getPullRequestClosedEvent())
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 2)

        self.executor_server.hold_jobs_in_build = True
        self.orderedRelease()
        self.assertHistory([
            dict(name='post-job', result='SUCCESS', ref=aref),
            dict(name='post-job', result='SUCCESS', ref=bref),
        ], ordered=False)
