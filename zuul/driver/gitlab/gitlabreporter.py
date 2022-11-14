# Copyright 2019 Red Hat, Inc.
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

import time
import logging
import voluptuous as v

from zuul import model
from zuul.reporter import BaseReporter
from zuul.lib.logutil import get_annotated_logger
from zuul.driver.gitlab.gitlabsource import GitlabSource
from zuul.driver.util import scalar_or_list
from zuul.exceptions import MergeFailure


class GitlabReporter(BaseReporter):
    """Sends off reports to Gitlab."""

    name = 'gitlab'
    log = logging.getLogger("zuul.GitlabReporter")

    # Merge modes supported by gitlab
    merge_modes = {
        model.MERGER_MERGE: 'merge',
        model.MERGER_MERGE_RESOLVE: 'merge',
        model.MERGER_SQUASH_MERGE: 'squash'
    }

    def __init__(self, driver, connection, pipeline, config=None):
        super(GitlabReporter, self).__init__(driver, connection, config)
        self._create_comment = self.config.get('comment', True)
        self._approval = self.config.get('approval', None)
        self._merge = self.config.get('merge', False)
        self._labels = self.config.get('label', [])
        if not isinstance(self._labels, list):
            self._labels = [self._labels]
        self._unlabels = self.config.get('unlabel', [])
        if not isinstance(self._unlabels, list):
            self._unlabels = [self._unlabels]

    def report(self, item, phase1=True, phase2=True):
        """Report on an event."""
        if not isinstance(item.change.project.source, GitlabSource):
            return

        if item.change.project.source.connection.canonical_hostname != \
                self.connection.canonical_hostname:
            return

        if hasattr(item.change, 'number'):
            if phase1:
                if self._create_comment:
                    self.addMRComment(item)
                if self._approval is not None:
                    self.setApproval(item)
                if self._labels or self._unlabels:
                    self.setLabels(item)
            if phase2 and self._merge:
                self.mergeMR(item)
                if not item.change.is_merged:
                    msg = self._formatItemReportMergeConflict(item)
                    self.addMRComment(item, msg)

    def addMRComment(self, item, comment=None):
        log = get_annotated_logger(self.log, item.event)
        message = comment or self._formatItemReport(item)
        project = item.change.project.name
        mr_number = item.change.number
        log.debug('Reporting change %s, params %s, message: %s',
                  item.change, self.config, message)
        self.connection.commentMR(project, mr_number, message,
                                  event=item.event)

    def setApproval(self, item):
        log = get_annotated_logger(self.log, item.event)
        project = item.change.project.name
        mr_number = item.change.number
        patchset = item.change.patchset
        log.debug('Reporting change %s, params %s, approval: %s',
                  item.change, self.config, self._approval)
        self.connection.approveMR(project, mr_number, patchset,
                                  self._approval, event=item.event)

    def setLabels(self, item):
        log = get_annotated_logger(self.log, item.event)
        project = item.change.project.name
        mr_number = item.change.number
        log.debug('Reporting change %s, params %s, labels: %s, unlabels: %s',
                  item.change, self.config, self._labels, self._unlabels)
        self.connection.updateMRLabels(project, mr_number,
                                       self._labels, self._unlabels,
                                       zuul_event_id=item.event)

    def mergeMR(self, item):
        project = item.change.project.name
        mr_number = item.change.number

        merge_mode = item.current_build_set.getMergeMode()

        if merge_mode not in self.merge_modes:
            mode = model.get_merge_mode_name(merge_mode)
            self.log.warning('Merge mode %s not supported by Gitlab', mode)
            raise MergeFailure('Merge mode %s not supported by Gitlab' % mode)

        merge_mode = self.merge_modes[merge_mode]

        for i in [1, 2]:
            try:
                self.connection.mergeMR(project, mr_number, merge_mode)
                item.change.is_merged = True
                return
            except MergeFailure:
                self.log.exception(
                    'Merge attempt of change %s  %s/2 failed.' %
                    (item.change, i), exc_info=True)
                if i == 1:
                    time.sleep(2)
        self.log.warning(
            'Merge of change %s failed after 2 attempts, giving up' %
            item.change)

    def getSubmitAllowNeeds(self):
        return []


def getSchema():
    gitlab_reporter = v.Schema({
        'comment': bool,
        'approval': bool,
        'merge': bool,
        'label': scalar_or_list(str),
        'unlabel': scalar_or_list(str),
    })
    return gitlab_reporter
