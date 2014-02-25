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

import testtools

import tests.base

FIXTURE_DIR = os.path.join(os.path.dirname(__file__),
                           'fixtures')
CONFIG = ConfigParser.ConfigParser()
CONFIG.read(os.path.join(FIXTURE_DIR, "zuul_poll.conf"))

CONFIG.set('zuul', 'layout_config',
           os.path.join(FIXTURE_DIR, "layout.yaml"))

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestMergerPoll(tests.base.TestSupportMixin, testtools.TestCase):
    TEST_CONFIG = CONFIG

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
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(B.addApproval('APRV', 1))
        self.waitUntilSettled()

        self.worker.release('.*-merge')
        self.waitUntilSettled()
        self.worker.release('.*-merge')
        self.waitUntilSettled()

        self.fake_gerrit.addEvent(C.addApproval('APRV', 1))
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(D.addApproval('APRV', 1))
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(E.addApproval('APRV', 1))
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
