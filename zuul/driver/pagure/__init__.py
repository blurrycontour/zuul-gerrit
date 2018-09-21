from zuul.driver import Driver, ConnectionInterface, TriggerInterface
from zuul.driver import SourceInterface, ReporterInterface
from zuul.driver.pagure import pagureconnection
from zuul.driver.pagure import paguresource
from zuul.driver.pagure import pagurereporter
from zuul.driver.pagure import paguretrigger

from zuul.trigger import BaseTrigger


class PagureDriver(Driver, ConnectionInterface, TriggerInterface,
                   SourceInterface, ReporterInterface):
    name = 'pagure'

    def getConnection(self, name, config):
        return pagureconnection.PagureConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return BaseTrigger(self, connection, config)

    def getSource(self, connection):
        return paguresource.PagureSource(self, connection)

    def getReporter(self, connection, pipeline, config=None):
        return pagurereporter.PagureReporter(
            self, connection, pipeline, config)

    def getTriggerSchema(self):
        return paguretrigger.getSchema()

    def getReporterSchema(self):
        return pagurereporter.getSchema()

    def getRequireSchema(self):
        return paguresource.getRequireSchema()

    def getRejectSchema(self):
        return paguresource.getRejectSchema()
