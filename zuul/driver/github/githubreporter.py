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
import time

from zuul.reporter import BaseReporter
from zuul.exceptions import MergeFailure


class GithubReporter(BaseReporter):
    """Sends off reports to Github."""

    name = 'github'
    log = logging.getLogger("zuul.GithubReporter")

    def __init__(self, driver, connection, config=None):
        super(GithubReporter, self).__init__(driver, connection, config)
        self._github_status_value = None
        self._set_commit_status = self.config.get('status', False)
        self._status_url = self.config.get('status_url', '')
        self._create_comment = self.config.get('comment', False)
        self._merge = self.config.get('merge', False)
        self._labels = self.config.get('label', [])
        if not isinstance(self._labels, list):
            self._labels = [self._labels]

    def postConfig(self):
        github_status_values = {
            'start': 'pending',
            'success': 'success',
            'failure': 'failure',
            'merge-failure': 'failure'
        }
        self._github_status_value = github_status_values[self._action]

    def report(self, source, pipeline, item):
        """Comment on PR and set commit status."""
        if self._create_comment:
            self.addPullComment(pipeline, item)
        if (self._set_commit_status and
            hasattr(item.change, 'patchset') and
            item.change.patchset is not None):
            self.setPullStatus(pipeline, item)
        if (self._merge and
            hasattr(item.change, 'number')):
            self.mergePull(item)
        if self._labels:
            self.setLabels(item)

    def addPullComment(self, pipeline, item):
        message = self._formatItemReport(pipeline, item)
        owner, project = item.change.project.name.split('/')
        pr_number = item.change.number
        self.log.debug(
            'Reporting change %s, params %s, message: %s' %
            (item.change, self.config, message))
        self.connection.commentPull(owner, project, pr_number, message)

    def setPullStatus(self, pipeline, item):
        owner, project = item.change.project.name.split('/')
        sha = item.change.patchset
        context = pipeline.name
        state = self._github_status_value

        url = ''
        if self._action == 'start':
            if self._status_url:
                # Check for a status_url in the reporter (from layout.yaml)
                url = item.formatUrlPattern(self._status_url)
            elif self.connection.sched.config.has_option('zuul', 'status_url'):
                # Fall back to the zuul server status_url (from zuul.conf)
                url = self.connection.sched.config.get('zuul', 'status_url')
                if self.connection.sched.config.has_option(
                        'zuul', 'status_url_with_change'):
                    url = '%s/#%s,%s' % (url,
                                         item.change.number,
                                         item.change.patchset)
        description = ''
        if pipeline.description:
            description = pipeline.description

        self.log.debug(
            'Reporting change %s, params %s, status:\n'
            'context: %s, state: %s, description: %s, url: %s' %
            (item.change, self.config, context, state,
             description, url))

        self.connection.setCommitStatus(
            owner, project, sha, state, url, description, context)

    def mergePull(self, item):
        owner, project = item.change.project.name.split('/')
        pr_number = item.change.number
        sha = item.change.patchset
        self.log.debug('Reporting change %s, params %s, merging via API' %
                       (item.change, self.config))
        message = self._formatMergeMessage(item.change)
        try:
            self.connection.mergePull(owner, project, pr_number, message, sha)
        except MergeFailure:
            time.sleep(2)
            self.log.debug('Trying to merge change %s again...' % item.change)
            self.connection.mergePull(owner, project, pr_number, message, sha)
        item.change.is_merged = True

    def setLabels(self, item):
        owner, project = item.change.project.name.split('/')
        pr_number = item.change.number
        self.log.debug('Reporting change %s, params %s, labels:\n%s' %
                       (item.change, self.config, self._labels))
        for label in self._labels:
            if label.startswith('-'):
                self.connection.unlabelPull(
                    owner, project, pr_number, label[1:])
            else:
                self.connection.labelPull(owner, project, pr_number, label)

    def _formatMergeMessage(self, change):
        message = ''

        if change.title:
            message += change.title

        account = change.source_event.account
        if not account:
            return message

        username = account['username']
        name = account['name']
        email = account['email']
        message += '\n\nReviewed-by: '

        if name:
            message += name
        if email:
            if name:
                message += ' '
            message += '<' + email + '>'
        if name or email:
            message += '\n             '
        message += self.connection.getUserUri(username)

        return message


def getSchema():
    def toList(x):
        return v.Any([x], x)

    github_reporter = v.Schema({
        'status': bool,
        'comment': bool,
        'merge': bool,
        'label': toList(str),
        'status_url': toList(str)
    })
    return github_reporter
