#!/usr/bin/env python

# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2014 Wikimedia Foundation Inc.
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

import argparse
import logging
import os

import git

import zuul.lib.cloner

from tests.base import ZuulTestCase
from tests.base import FIXTURE_DIR

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestCloner(ZuulTestCase):

    def test_cloner(self):
        log = logging.getLogger("zuul.test.cloner")

        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-gating.yaml')
        self.sched.reconfigure(self.config)
        self.registerJobs()

        self.worker.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        A.addPatchset(['project_one.txt'])
        B.addPatchset(['project_two.txt'])
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))

        A.addApproval('CRVW', 2)
        B.addApproval('CRVW', 2)
        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))
        self.fake_gerrit.addEvent(B.addApproval('APRV', 1))

        self.waitUntilSettled()

        self.assertEquals(2, len(self.builds), "Two builds are running")

        a_zuul_ref = b_zuul_ref = None
        log.debug("# of builds: %s" % len(self.builds))
        for build in self.builds:
            log.debug("Build parameters: %s", build.parameters)
            if build.parameters['ZUUL_CHANGE'] == '1':
                a_zuul_ref = build.parameters['ZUUL_REF']
            if build.parameters['ZUUL_CHANGE'] == '2':
                b_zuul_ref = build.parameters['ZUUL_REF']

        log.debug("Refs are: A: %s B: %s" % (a_zuul_ref, b_zuul_ref))
        self.assertIsNotNone(a_zuul_ref, 'Can not find Zuul ref for change A')
        self.assertIsNotNone(b_zuul_ref, 'Can not find Zuul ref for change B')

        zuul_repo1 = git.Repo(os.path.join(self.git_root, 'org/project1'))
        log.debug("Zuul repo1 references: %s" % zuul_repo1.references)
        zuul_repo2 = git.Repo(os.path.join(self.git_root, 'org/project2'))
        log.debug("Zuul repo2 references: %s" % zuul_repo2.references)

        # 2 refs
        zuul_repo1_zref = [ref.path for ref in zuul_repo1.references
                           if ref.path.startswith('refs/zuul/')]
        zuul_repo2_zref = [ref.path for ref in zuul_repo2.references
                           if ref.path.startswith('refs/zuul/')]

        self.assertIn(a_zuul_ref, zuul_repo1_zref)
        self.assertIn(b_zuul_ref, zuul_repo1_zref)
        self.assertIn(b_zuul_ref, zuul_repo2_zref)

        self.worker.hold_jobs_in_build = False
        self.worker.release()
        self.waitUntilSettled()

        # Repos setup, now test the cloner

        # Debug statement to copy the git repos under /tmp/
        if False:
            import shutil
            shutil.copytree(
                os.path.join(self.upstream_root, 'org/project1'),
                '/tmp/zuulupstreamroot')
            shutil.copytree(
                os.path.join(self.git_root, 'org/project1'),
                '/tmp/zuulgitroot')

        workspace_root = os.path.join(self.test_root, 'workspace')
        os.makedirs(workspace_root)

        cloner = zuul.lib.cloner.Cloner(
            argparse.Namespace(
                verbose=True,
                projects=['org/project1', 'org/project2'],
                clone_map_file=os.path.join(FIXTURE_DIR, 'clonemap.yaml'),
                gitbaseurl=self.upstream_root,
                workspace=workspace_root,
                zuul_url=self.git_root,
                zuul_ref=a_zuul_ref,
                zuul_branch='master',
                branch='master'
            )
        )
        cloner.execute()

        cloner = zuul.lib.cloner.Cloner(
            argparse.Namespace(
                verbose=True,
                projects=['org/project1', 'org/project2'],
                clone_map_file=os.path.join(FIXTURE_DIR, 'clonemap.yaml'),
                gitbaseurl=self.upstream_root,
                workspace=workspace_root,
                zuul_url=self.git_root,
                zuul_ref=b_zuul_ref,
                zuul_branch='master',
                branch='master'
            )
        )
        cloner.execute()

        if False:
            # TODO inspect the repositories in the workspace
            work_repo1 = git.Repo(os.path.join(workspace_root, 'org/project1'))
            log.debug("Work Repo1 origin refs: %s",
                      work_repo1.remotes.origin.refs)
            log.debug("Work Repo1 references: %s" % work_repo1.references)
            log.debug("Work Repo1 HEAD is %s", work_repo1.commit('HEAD'))
            log.debug("Work Repo1 URL: %s", work_repo1.remote().url)
            log.debug("Work Repo1 heads: %s", work_repo1.heads)
            log.debug("Work Repo1 branches: %s", work_repo1.branches)

            work_repo2 = git.Repo(os.path.join(workspace_root, 'org/project2'))
            log.debug("Work Repo2 origin refs: %s",
                      work_repo2.remotes.origin.refs)
            log.debug("Work Repo2 references: %s" % work_repo2.references)
            log.debug("Work Repo2 HEAD is %s", work_repo1.commit('HEAD'))
            log.debug("Work Repo2 URL: %s", work_repo2.remote().url)
            log.debug("Work Repo2 heads: %s", work_repo2.heads)
            log.debug("Work Repo2 branches: %s", work_repo2.branches)
