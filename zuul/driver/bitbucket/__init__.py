
from zuul.driver import Driver, ConnectionInterface
from zuul.driver import SourceInterface, ReporterInterface
from zuul.driver.bitbucket import bitbucketconnection
from zuul.driver.bitbucket import bitbucketsource
from zuul.dirver.bitbucket import bitbucketreporter


class BitbucketDriver(Driver, ConnectionInterface, SourceInterface,
                      ReporterInterface):
    name = 'bitbucket'

    def getConnection(self, name, config):
        return bitbucketconnection.BitbucketConnection(self, name, config)

    def getSource(self, connection):
        return bitbucketsource.BitbucketSource(self, connection)

    def getRequireSchema(self):
        return {}

    def getRejectSchema(self):
        return {}

    def getReporter(self, connection, pipeline, config=None):
        return bitbucketreporter.BitbucketReporter(
            self, connection, pipeline, config)

    def getReporterSchema(self):
        return bitbucketreporter.getSchema()
