from zuul.driver import Driver, ConnectionInterface, TriggerInterface
from zuul.driver import SourceInterface
from zuul.driver.bitbucketserver import bitbucketserverconnection
from zuul.driver.bitbucketserver import bitbucketserversource
from zuul.driver.bitbucketserver import bitbucketservertrigger


class BitbucketServerDriver(Driver, ConnectionInterface, TriggerInterface, SourceInterface):
    name = 'bitbucketserver'

    def getConnection(self, name, config):
        return bitbucketserverconnection.BitbucketServerConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return bitbucketservertrigger.BitbucketServerTrigger(self, connection, config)

    def getSource(self, connection):
        return bitbucketserversource.BitbucketServerSource(self, connection)

    def getTriggerSchema(self):
        return bitbucketservertrigger.getSchema()

    def getRequireSchema(self):
        return bitbucketserversource.getRequireSchema()

    def getRejectSchema(self):
        return bitbucketserversource.getRejectSchema()
