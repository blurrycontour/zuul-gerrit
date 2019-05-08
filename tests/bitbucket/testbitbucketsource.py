import unittest
from unittest.mock import patch

from zuul.driver.bitbucket.bitbucketmodel import PullRequest
from tests.bitbucket.mocks import BitbucketClientMock, CommonConnectionTest

class TestBitbucketSource(CommonConnectionTest):

	def _source(self):
		c = self._connection()
		return c.source

	def test_getProject(self):
		con = self._connection()
		p = con.getProject(self.realProject)
		self.assertEqual(p.name, self.realProject)

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getProjectBranches(self):
		s = self._source()
		p = s.getProject(self.realProject)
		b = s.getProjectBranches(p, 'default')
		self.assertEqual(len(b), 3)
		self.assertTrue('master' in b)

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getProjectOpenChanges(self):
		s = self._source()
		project = s.getProject(self.realProject)
		change = s.getChangeByURL('https://bitbucket.glumfungl.net/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101')

		changes = s.getProjectOpenChanges(project)

		self.assertEqual(len(changes), 1)
		self.assertTrue(change in changes)

	def test_getGitUrl(self):
		s = self._source()
		proj = s.getProject(self.realProject)
		url = s.getGitUrl(proj)
		self.assertEqual(url, self.realGitUrl)

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getRefSha(self):
		s = self._source()
		p = s.getProject('foobar')
		with self.assertRaises(NotImplementedError):
			s.getRefSha(p, 'xxxxx')

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_waitForRefSha(self):
		s = self._source()
		p = s.getProject('foobar')
		with self.assertRaises(NotImplementedError):
			s.waitForRefSha(p, 'xxxxx')

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getChangeByURL(self):
		s = self._source()
		project = s.getProject(self.realProject)
		change = s.getChangeByURL('https://bitbucket.glumfungl.net/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101')
		self.assertIsInstance(change, PullRequest)
		self.assertEqual(change.id, 101)
		self.assertEqual(change.project, project)

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_canMerge(self):
		s = self._source()
		project = s.getProject(self.realProject)
		change = s.getChangeByURL('https://bitbucket.glumfungl.net/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101')
		self.assertFalse(s.canMerge(change, False))

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_isMerged(self):
		s = self._source()
		project = s.getProject(self.realProject)
		change = s.getChangeByURL('https://bitbucket.glumfungl.net/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101')
		self.assertFalse(s.isMerged(change, 'xyz'))

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getChange(self):
		s = self._source()
		with self.assertRaises(NotImplementedError):
			change = s.getChange('xxx')

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getChangesDependingOn(self):
		s = self._source()
		project = s.getProject(self.realProject)
		change = s.getChangeByURL('https://bitbucket.glumfungl.net/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101')
		self.assertEqual([], s.getChangesDependingOn(change, [project], 'default'))

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getRejectFilters(self):
		s = self._source()
		self.assertEqual(s.getRejectFilters(), [])

	@patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient', new=BitbucketClientMock)
	def test_getRequireFilters(self):
		s = self._source()
		self.assertEqual(s.getRequireFilters(), [])
