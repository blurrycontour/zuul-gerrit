
from zuul.driver.bitbucket import BitbucketDriver
from zuul.driver.bitbucket.bitbucketsource import BitbucketSource
from zuul.driver.bitbucket.bitbucketconnection import BitbucketConnection
from zuul.driver.bitbucket.bitbucketreporter import BitbucketReporter
from tests.base import BaseTestCase
from voluptuous import Schema
from unittest.mock import MagicMock


class TestBitbucketDriver(BaseTestCase):
    def test_getRequireSchema(self):
        drv = BitbucketDriver()
        self.assertEqual({}, drv.getRequireSchema())

    def test_getRejectSchema(self):
        drv = BitbucketDriver()
        self.assertEqual({}, drv.getRejectSchema())

    def test_getSource(self):
        drv = BitbucketDriver()
        self.assertIsInstance(drv.getSource(drv.getConnection('foo', {})),
                              BitbucketSource)

    def test_getConnection(self):
        drv = BitbucketDriver()
        self.assertIsInstance(drv.getConnection('foo', {}),
                              BitbucketConnection)

    def test_getReporter(self):
        drv = BitbucketDriver()
        pipeline = MagicMock()
        pipeline.tenant = MagicMock()
        pipeline.tenant.name = 'foobar'
        pipeline.name = 'blorb'
        self.assertIsInstance(drv.getReporter('foo', pipeline, {}),
                              BitbucketReporter)

    def test_getReportSchema(self):
        drv = BitbucketDriver()
        scm = drv.getReporterSchema()
        self.assertIsInstance(scm, Schema)
