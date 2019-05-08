import unittest

from os import environ
from unittest.mock import patch
from tests.unit.bitbucket.mocks import BitbucketClientMock,\
    CommonConnectionTest
from zuul.driver.bitbucket.bitbucketconnection import\
    BitbucketClient, BitbucketConnectionError
from tests.base import BaseTestCase


class TestBitbucketClient(BaseTestCase):

    def _broken_client(self):
        bc = BitbucketClient("https://bitbucket.glumfun.test", 443)
        bc.setCredentials("mark", "foobar")
        return bc

    def _client(self):
        bc = BitbucketClient(environ['BITBUCKET_SERVER'], 443)
        bc.setCredentials(environ['BITBUCKET_USER'], environ['BITBUCKET_PASS'])
        return bc

    @unittest.skip
    def test_authenticateFailed(self):
        with self.assertRaises(BitbucketConnectionError):
            bc = self._broken_client()
            bc.get("/projects")

    @unittest.skip
    def test_notFound(self):
        with self.assertRaises(BitbucketConnectionError):
            bc = self._client()
            bc.get("jects")

    @unittest.skip
    def test_authenticateSuccessfulAndFound(self):
        bc = self._client()
        self.assertGreater(len(bc.get("/projects")), 0)


class TestBitbucketConnection(CommonConnectionTest):

    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketClient',
           new=BitbucketClientMock)
    def test_getBitbucketClient(self):
        con = self._connection()
        client = con._getBitbucketClient()
        self.assertEqual(client.user, 'mark')
        self.assertEqual(client.pw, 'foobar')
        self.assertEqual(client.server, 'https://bitbucket.glumfun.test')
        self.assertEqual(client.port, 43)

    @unittest.skip
    def test_getWebUrl(self):
        con = self._connection()
        proj = con.getProject(self.realProject)
        url = con.getWebUrl(proj)
        self.assertIsNotNone(url)
        self.assertEqual(url, self.realWebUrl)

    @unittest.skip
    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketWatcher')
    def test_onLoad(self, bw_mock):
        con = self._connection()
        con.onLoad()

        inst = bw_mock.return_value
        self.assertTrue(inst.start.assert_called_once_with())

    @unittest.skip
    @patch('zuul.driver.bitbucket.bitbucketconnection.BitbucketWatcher')
    def test_onStop(self, bw_mock):
        con = self._connection()
        con.onLoad()
        con.onStop()

        inst = bw_mock.return_value
        self.assertTrue(inst.start.assert_called_once_with())
        self.assertTrue(inst.stop.assert_called_once_with())
        self.assertTrue(inst.join.assert_called_once_with())
