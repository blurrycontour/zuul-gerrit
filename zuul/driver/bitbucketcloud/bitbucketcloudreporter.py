# Copyright 2015 Puppet Labs
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

import logging
import voluptuous as v
from zuul.lib.logutil import get_annotated_logger
from zuul.reporter import BaseReporter
from zuul.driver.bitbucketcloud.bitbucketcloudsource import (
    BitbucketCloudSource)


class BitbucketCloudReporter(BaseReporter):
    """Sends off reports to BitbucketCloud."""

    name = 'bitbucketcloud'
    log = logging.getLogger("zuul.BitbucketCloudReporter")

    def __init__(self, driver, connection, pipeline, config=None):
        super(
            BitbucketCloudReporter,
            self).__init__(
            driver,
            connection,
            config)

        self._commit_status = self.config.get('status', None)
        self._create_comment = self.config.get('comment', False)
        self._review = self.config.get('review')
        self.context = "{}/{}".format(pipeline.tenant.name, pipeline.name)

    def report(self, item):
        """Report on an event."""
        # If the source is not BitbucketCloudSource we cannot report anything
        # here.
        if not isinstance(item.change.project.source, BitbucketCloudSource):
            return

        # TODO For supporting several BitbucketCloud connections it's
        # also needed to filter by the canonical hostname + workspace,
        # as differentiating repos would use
        # bitbucket.org/<workspace>/<repo>, where workspace is the "target"
        if item.change.project.source.connection.canonical_hostname != \
                self.connection.canonical_hostname:
            return

        if self._commit_status is not None:
            if (hasattr(item.change, 'patchset') and
                    item.change.patchset is not None):
                self.setCommitStatus(item)
            elif (hasattr(item.change, 'newrev') and
                    item.change.newrev is not None):
                self.setCommitStatus(item)

        # Comments can only be performed on pull requests.
        # If the change is not a pull request (e.g. a push) skip them.
        if hasattr(item.change, 'number'):
            if self._review:
                self.addReview(item)

            if self._create_comment:  # or errors_received:
                self.addPullComment(item)

    def _formatItemReportJobs(self, item):
        # Return the list of jobs portion of the report
        ret = ''
        jobs_fields = self._getItemReportJobsFields(item)
        for job_fields in jobs_fields:
            ret += '- [%s](%s) : %s%s%s%s\n' % job_fields
        return ret

    def addPullComment(self, item, comment=None):
        log = get_annotated_logger(self.log, item.event)
        message = comment or self._formatItemReport(item)
        project = item.change.project.name
        pr_number = item.change.number
        log.debug('Reporting change %s, params %s, message: %s',
                  item.change, self.config, message)
        self.connection.commentPull(project, pr_number, message,
                                    zuul_event_id=item.event)

    def setCommitStatus(self, item):
        log = get_annotated_logger(self.log, item.event)

        project = item.change.project.name
        if hasattr(item.change, 'patchset'):
            sha = item.change.patchset
        elif hasattr(item.change, 'newrev'):
            sha = item.change.newrev
        state = self._commit_status
        url = item.formatStatusUrl()

        description = '%s status: %s' % (item.pipeline.name,
                                         self._commit_status)
        log.debug(
            'Reporting change %s, params %s, '
            'context: %s, state: %s, description: %s, url: %s',
            item.change, self.config, self.context, state, description, url)

        self.connection.setCommitStatus(
            project, sha, state, url, description, self.context,
            zuul_event_id=item.event)

    def addReview(self, item):
        log = get_annotated_logger(self.log, item.event)
        project = item.change.project.name
        pr_number = item.change.number
        sha = item.change.patchset
        log.debug('Reporting change %s, params %s, review:\n%s',
                  item.change, self.config, self._review)
        self.connection.reviewPull(
            project,
            pr_number,
            sha,
            self._review,
            zuul_event_id=item.event)


def getSchema():
    BitbucketCloud_reporter = v.Schema({
        'status': v.Any('INPROGRESS', 'SUCCESSFUL', 'FAILED', 'STOPPED'),
        'status-url': str,
        'comment': bool,
        'review': v.Any('approve', 'unapprove', 'decline'),
    })
    return BitbucketCloud_reporter
