# Copyright 2019 Smaato, Inc.
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

from unittest.mock import patch
import unittest

from zuul.driver.bitbucket.bitbucketmodel import PullRequest
from tests.unit.bitbucket.mocks import BitbucketClientMock,\
    CommonConnectionTest


class TestBitbucketSource(CommonConnectionTest):

    def _source(self):
        c = self._connection()
        return c.source

    def test_getProject(self):
        con = self._connection()
        p = con.getProject(self.realProject)
        self.assertEqual(p.name, self.realProject)

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getProjectBranches(self):
        s = self._source()
        p = s.getProject(self.realProject)
        b = s.getProjectBranches(p, 'default')
        self.assertEqual(len(b), 3)
        self.assertTrue('master' in b)

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getProjectOpenChanges(self):
        s = self._source()
        project = s.getProject(self.realProject)
        change = s.getChangeByURL('https://bitbucket.glumfun.test/rest/api/'
                                  '1.0/projects/sys-ic/repos/foobar/'
                                  'pull-requests/101')

        changes = s.getProjectOpenChanges(project)

        self.assertEqual(len(changes), 1)
        self.assertTrue(change in changes)

    def test_getGitUrl(self):
        s = self._source()
        proj = s.getProject(self.realProject)
        url = s.getGitUrl(proj)
        self.assertEqual(url, self.realGitUrl)

    @unittest.skip
    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getRefSha(self):
        s = self._source()
        p = s.getProject('foobar')
        with self.assertRaises(NotImplementedError):
            s.getRefSha(p, 'xxxxx')

    @unittest.skip
    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_waitForRefSha(self):
        s = self._source()
        p = s.getProject('foobar')
        with self.assertRaises(NotImplementedError):
            s.waitForRefSha(p, 'xxxxx')

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getChangeByURL(self):
        s = self._source()
        project = s.getProject(self.realProject)
        change = s.getChangeByURL('https://bitbucket.glumfun.test/rest/'
                                  'api/1.0/projects/sys-ic/repos/foobar/'
                                  'pull-requests/101')
        self.assertIsInstance(change, PullRequest)
        self.assertEqual(change.id, 101)
        self.assertEqual(change.project, project)

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_canMerge(self):
        s = self._source()
        change = s.getChangeByURL('https://bitbucket.glumfun.test/rest/'
                                  'api/1.0/projects/sys-ic/repos/foobar/'
                                  'pull-requests/101')
        self.assertFalse(s.canMerge(change, False))

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_isMerged(self):
        s = self._source()
        change = s.getChangeByURL('https://bitbucket.glumfun.test/rest/'
                                  'api/1.0/projects/sys-ic/repos/foobar/'
                                  'pull-requests/101')
        self.assertFalse(s.isMerged(change, 'xyz'))

    @unittest.skip
    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getChange(self):
        s = self._source()
        with self.assertRaises(NotImplementedError):
            s.getChange('xxx')

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getChangesDependingOn(self):
        s = self._source()
        project = s.getProject(self.realProject)
        change = s.getChangeByURL('https://bitbucket.glumfun.test/rest/'
                                  'api/1.0/projects/sys-ic/repos/foobar/'
                                  'pull-requests/101')
        self.assertEqual([], s.getChangesDependingOn(change, [project],
                                                     'default'))

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getRejectFilters(self):
        s = self._source()
        self.assertEqual(s.getRejectFilters(), [])

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getRequireFilters(self):
        s = self._source()
        self.assertEqual(s.getRequireFilters(), [])
