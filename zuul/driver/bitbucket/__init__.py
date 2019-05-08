
from zuul.driver import Driver, ConnectionInterface
from zuul.driver import SourceInterface
from zuul.driver.bitbucket import bitbucketconnection
from zuul.driver.bitbucket import bitbucketsource


class BitbucketDriver(Driver, ConnectionInterface, SourceInterface):
    name = 'bitbucket'

    def getConnection(self, name, config):
        return bitbucketconnection.BitbucketConnection(self, name, config)

    def getSource(self, connection):
        return bitbucketsource.BitbucketSource(self, connection)

    def getRequireSchema(self):
        return {}

    def getRejectSchema(self):
        return {}
