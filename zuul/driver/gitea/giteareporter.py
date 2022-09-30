# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2018 Red Hat, Inc.
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

from zuul.model import MERGER_MERGE_RESOLVE, MERGER_MERGE, MERGER_MAP, \
    MERGER_SQUASH_MERGE
from zuul.lib.logutil import get_annotated_logger
from zuul.reporter import BaseReporter
from zuul.exceptions import MergeFailure
from zuul.driver.gitea.giteasource import GiteaSource


class GiteaReporter(BaseReporter):
    """Sends off reports to Gitea."""

    name = 'gitea'
    log = logging.getLogger("zuul.GiteaReporter")

    # Merge modes supported by github
    merge_modes = {
        MERGER_MERGE: 'merge',
        MERGER_MERGE_RESOLVE: 'merge',
        MERGER_SQUASH_MERGE: 'squash',
    }

    def __init__(self, driver, connection, pipeline, config=None,
                 parse_context=None):
        super().__init__(driver, connection, config, parse_context)
        self._commit_status = self.config.get('status', None)
        self._create_comment = self.config.get('comment', True)
        self._merge = self.config.get('merge', False)
        self.context = "{}/{}".format(pipeline.tenant.name, pipeline.name)

    def report(self, item, phase1=True, phase2=True):
        """Report on an event."""
        for change in item.changes:
            self._reportChange(item, change, phase1, phase2)

    def _reportChange(self, item, change, phase1=True, phase2=True):
        """Report on an event."""

        # If the source is not GiteaSource we cannot report anything here.
        if not isinstance(change.project.source, GiteaSource):
            return

        # For supporting several Gitea connections we also must filter by
        # the canonical hostname.
        if change.project.source.connection.canonical_hostname != \
                self.connection.canonical_hostname:
            return

        # order is important for branch protection.
        # A status should be set before a merge attempt
        if phase1 and self._commit_status is not None:
            if self._commit_status is not None:
                if (hasattr(change, 'patchset') and
                        change.patchset is not None):
                    self.setCommitStatus(item, change)
                elif (hasattr(change, 'newrev') and
                        change.newrev is not None):
                    self.setCommitStatus(item, change)
        # Comments, labels, and merges can only be performed on pull requests.
        # If the change is not a pull request (e.g. a push) skip them.
        if hasattr(change, 'number'):
            errors_received = False
            if phase1:
                if self._create_comment or errors_received:
                    self.addPullComment(item, change)
            if phase2 and self._merge:
                self.mergePull(item, change)
                if not change.is_merged:
                    msg = self._formatItemReportMergeConflict(item, change)
                    self.addPullComment(item, change, msg)

    def _formatItemReportJobs(self, item):
        # Return the list of jobs portion of the report
        ret = ''
        jobs_fields, skipped = self._getItemReportJobsFields(item)
        for job_fields in jobs_fields:
            ret += '- [%s](%s): %s%s%s%s\n' % job_fields[:6]
        if skipped:
            jobtext = 'job' if skipped == 1 else 'jobs'
            ret += 'Skipped %i %s\n' % (skipped, jobtext)
        return ret

    def addPullComment(self, item, change, comment=None):
        message = comment or self._formatItemReport(item)
        project = change.project.name
        pr_number = change.number
        self.log.debug(
            'Reporting change %s, params %s, message: %s' %
            (change, self.config, message))
        self.connection.commentPull(project, pr_number, message)

    def setCommitStatus(self, item, change):
        project = change.project.name
        if hasattr(change, 'patchset'):
            sha = change.patchset
        elif hasattr(change, 'newrev'):
            sha = change.newrev
        state = self._commit_status

        url = item.formatItemUrl()

        description = '%s status: %s (%s)' % (
            item.pipeline.name, self._commit_status, sha)

        self.log.debug(
            'Reporting change %s, params %s, '
            'context: %s, state: %s, description: %s, url: %s' %
            (change, self.config,
             self.context, state, description, url))

        self.connection.setCommitStatus(
            project, sha, state, url, description, self.context)

    def mergePull(self, item, change):
        log = get_annotated_logger(self.log, item.event)
        merge_mode = item.current_build_set.getMergeMode(change)

        if merge_mode not in self.merge_modes:
            mode = [x[0] for x in MERGER_MAP.items() if x[1] == merge_mode][0]
            self.log.warning('Merge mode %s not supported by Gitea', mode)
            raise MergeFailure('Merge mode %s not supported by Gitea' % mode)

        merge_mode = self.merge_modes[merge_mode]
        project = change.project.name
        pr_number = change.number
        sha = change.patchset
        self.log.debug(
            f"Reporting change {change}, params {self.config}, "
            f"merging via API"
        )
        error_message = None

        try:
            self.connection.mergePull(
                project, pr_number,
                merge_title=change.title,
                merge_message=self._formatMergeMessage(change),
                sha=sha, method=merge_mode,
                zuul_event_id=item.event)
            change.is_merged = True
            return
        except MergeFailure as e:
            log.exception(
                'Merge attempt of change %s failed.' %
                change, exc_info=True)
            error_message = str(e)
        log.warning(
            'Merge of change %s failed, giving up' % change)
        # Be friendly and report the failure as PR comment.
        self.addPullComment(item, f"Merging failed:\n\n{error_message}")
        raise MergeFailure(error_message)

    def getSubmitAllowNeeds(self):
        return []

    def _formatMergeMessage(self, change):
        merge_message = ''
        if change.reviews:
            review_users = []
            for r in change.reviews:
                name = r['user']['full_name']
                if not name:
                    name = r['user']['login']
                email = r['user']['email']
                review_users.append('Reviewed-by: {} <{}>'.format(name, email))
            merge_message += '\n'.join(review_users)
        return merge_message


def getSchema():
    gitea_reporter = v.Schema({
        'status': v.Any('pending', 'success',
                        'error', 'failure', 'warning'),
        'status-url': str,
        'comment': bool,
        'merge': bool,
    })
    return gitea_reporter
