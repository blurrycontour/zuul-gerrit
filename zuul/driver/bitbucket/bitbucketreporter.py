import logging
import voluptuous as v
import time

from zuul.reporter import BaseReporter
from zuul.exceptions import MergeFailure
from zuul.driver.bitbucket.bitbucketsource import BitbucketSource


class BitbucketReporter(BaseReporter):
    """Sends reports to Bitbucket, based on CodeInsights API"""

    name = 'bitbucket'
    log = logging.getLogger("zuul.BitbucketReporter")

    def __init__(self, driver, connection, pipeline, config=None):
        super(BitbucketReporter, self).__init__(driver, connection, config)

        self.context = "{}/{}".format(pipeline.tenant.name, pipeline.name)
        self._merge = self.config.get('merge', False)

    def report(self, item):
        if not isinstance(item.change.project.source, BitbucketSource):
            return

        if item.change.project.source.connection.server != \
                self.connection.server:
            return

        if hasattr(item.change, 'id'):
            self.setBuildStatus(item)
            if self._merge:
                self.mergePull(item)

    def mergePull(self, item):
        for i in [1, 2, 3, 4]:
            try:
                self.connection.mergePull(item.change.project, item.change.id)
                item.change.is_merged = True
                return
            except MergeFailure:
                self.log.exception(
                    'Merge attempt of change {} {}/4 failed.'
                    .format(item.change, i))
                time.sleep(2)
        self.log.warning(
            'Merge of change {} failed after 4 attempts, giving up',
            item.change)

    def setBuildStatus(self, item, comment=None):
        message = comment or self._formatItemReport(item)
        state = 'FAILED'
        if not item.areAllJobsComplete():
            state = 'INPROGRESS'
        if item.didAllJobsSucceed():
            state = 'SUCCESSFUL'
        status = {
            'state': state,
            'key': 'zuul-{}'.format(self.context),
            'name': 'Zuul: {}'.format(self.context),
            'url': 'https://zuul.test',  # FIXME
            'description': message
        }
        self.connection.setBuildStatus(item.change.patchset, status)


def getSchema():
    bitbucket_reporter = v.Schema({
    })
    return bitbucket_reporter
