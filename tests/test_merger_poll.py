#!/usr/bin/env python

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

import ConfigParser
import logging
import os
import time

import fixtures

from tests.base import FIXTURE_DIR, ZuulTestCase

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestMergerPoll(ZuulTestCase):
    def setUp(self):
        # Increase test timeout so that we can exercise poll delays.
        self.useFixture(fixtures.EnvironmentVariable('OS_TEST_TIMEOUT', '90'))
        super(TestMergerPoll, self).setUp()

    def setup_config(self):
        super(TestMergerPoll, self).setup_config()
        self.replica_root = os.path.join(self.test_root, "replica")
        os.makedirs(self.replica_root)

        self.config = ConfigParser.ConfigParser()
        self.config.read(os.path.join(FIXTURE_DIR, "zuul_poll.conf"))

        self.config.set('zuul', 'layout_config',
                        os.path.join(FIXTURE_DIR, "layout.yaml"))
        self.config.set('merger', 'git_dir', self.git_root)
        self.config.set('gerrit', 'fetch_url', self.replica_root)

    def setup_repos(self):
        super(TestMergerPoll, self).setup_repos()
        # Init replica_root
        self.clone_repo(self.upstream_root, self.replica_root, "org/project")
        self.clone_repo(self.upstream_root, self.replica_root, "org/project1")
        self.clone_repo(self.upstream_root, self.replica_root, "org/project2")
        self.clone_repo(self.upstream_root, self.replica_root, "org/project3")

    def test_parallel_changes_with_poll(self):
        "Test that changes are tested in parallel and merged in series"

        self.worker.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')
        C = self.fake_gerrit.addFakeChange('org/project', 'master', 'C')
        A.addApproval('CRVW', 2)
        B.addApproval('CRVW', 2)
        C.addApproval('CRVW', 2)

        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))
        self.fake_gerrit.addEvent(B.addApproval('APRV', 1))
        self.fake_gerrit.addEvent(C.addApproval('APRV', 1))

        # Exercise merger polling
        time.sleep(10)
        # Update merger fetch location so that it will have the commits
        self.update_repo(self.replica_root, "org/project")

        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.builds[0].name, 'project-merge')
        self.assertTrue(self.job_has_changes(self.builds[0], A))

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 3)
        self.assertEqual(self.builds[0].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[0], A))
        self.assertEqual(self.builds[1].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[1], A))
        self.assertEqual(self.builds[2].name, 'project-merge')
        self.assertTrue(self.job_has_changes(self.builds[2], A, B))

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 5)
        self.assertEqual(self.builds[0].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[0], A))
        self.assertEqual(self.builds[1].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[1], A))

        self.assertEqual(self.builds[2].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[2], A, B))
        self.assertEqual(self.builds[3].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[3], A, B))

        self.assertEqual(self.builds[4].name, 'project-merge')
        self.assertTrue(self.job_has_changes(self.builds[4], A, B, C))

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 6)
        self.assertEqual(self.builds[0].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[0], A))
        self.assertEqual(self.builds[1].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[1], A))

        self.assertEqual(self.builds[2].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[2], A, B))
        self.assertEqual(self.builds[3].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[3], A, B))

        self.assertEqual(self.builds[4].name, 'project-test1')
        self.assertTrue(self.job_has_changes(self.builds[4], A, B, C))
        self.assertEqual(self.builds[5].name, 'project-test2')
        self.assertTrue(self.job_has_changes(self.builds[5], A, B, C))

        self.worker.hold_jobs_in_build = False
        self.worker.release()
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 0)

        self.assertEqual(len(self.history), 9)
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertEqual(C.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)

    def test_dependent_behind_dequeue_with_poll(self):
        "test that dependent changes behind dequeued changes work"
        # This complicated test is a reproduction of a real life bug
        self.sched.reconfigure(self.config)

        self.worker.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')
        C = self.fake_gerrit.addFakeChange('org/project2', 'master', 'C')
        D = self.fake_gerrit.addFakeChange('org/project2', 'master', 'D')
        E = self.fake_gerrit.addFakeChange('org/project2', 'master', 'E')
        F = self.fake_gerrit.addFakeChange('org/project3', 'master', 'F')
        D.setDependsOn(C, 1)
        E.setDependsOn(D, 1)
        A.addApproval('CRVW', 2)
        B.addApproval('CRVW', 2)
        C.addApproval('CRVW', 2)
        D.addApproval('CRVW', 2)
        E.addApproval('CRVW', 2)
        F.addApproval('CRVW', 2)

        A.fail_merge = True

        # Change object re-use in the gerrit trigger is hidden if
        # changes are added in quick succession; waiting makes it more
        # like real life.
        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))
        # Exercise merger polling
        time.sleep(5)
        # Update merger fetch location so that it will have the commits
        self.update_repo(self.replica_root, "org/project1")
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(B.addApproval('APRV', 1))
        self.waitUntilSettled()

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.worker.release('.*-merge')
        self.waitUntilSettled()

        self.fake_gerrit.addEvent(C.addApproval('APRV', 1))
        # Exercise merger polling
        time.sleep(5)
        # Update merger fetch location so that it will have the commits
        self.update_repo(self.replica_root, "org/project2")
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(D.addApproval('APRV', 1))
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(E.addApproval('APRV', 1))
        # Exercise merger polling
        time.sleep(5)
        # Update merger fetch location so that it will have the commits
        self.update_repo(self.replica_root, "org/project3")
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(F.addApproval('APRV', 1))
        self.waitUntilSettled()

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.worker.release('.*-merge')
        self.waitUntilSettled()

        # all jobs running

        # Grab pointers to the jobs we want to release before
        # releasing any, because list indexes may change as
        # the jobs complete.
        a, b, c = self.builds[:3]
        a.release()
        b.release()
        c.release()
        self.waitUntilSettled()

        self.worker.hold_jobs_in_build = False
        self.worker.release()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'NEW')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertEqual(C.data['status'], 'MERGED')
        self.assertEqual(D.data['status'], 'MERGED')
        self.assertEqual(E.data['status'], 'MERGED')
        self.assertEqual(F.data['status'], 'MERGED')

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(D.reported, 2)
        self.assertEqual(E.reported, 2)
        self.assertEqual(F.reported, 2)

        self.assertEqual(self.countJobResults(self.history, 'ABORTED'), 15)
        self.assertEqual(len(self.history), 44)

    def test_merge_poll_timeout(self):
        "Test that merger reports failure after poll timeout"

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('CRVW', 2)

        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))

        # At this point zuul should process and attempt to merge the change
        # but the replica will not be updated so we should settle without
        # a successful merge.
        self.waitUntilSettled(timeout=65)
        self.assertEqual(A.data['status'], 'NEW')
