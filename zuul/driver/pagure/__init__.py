from zuul.driver import Driver, ConnectionInterface, TriggerInterface
from zuul.driver import SourceInterface, ReporterInterface
from zuul.driver.pagure import pagureconnection
from zuul.driver.pagure import paguresource

from zuul.trigger import BaseTrigger
from zuul.reporter import BaseReporter


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
        return BaseReporter(
            self, connection, pipeline, config)

    def getTriggerSchema(self):
        return None

    def getReporterSchema(self):
        return None

    def getRequireSchema(self):
        return None

    def getRejectSchema(self):
        return None
