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

from zuul.reporter import BaseReporter


class GithubReporter(BaseReporter):
    """Sends off reports to Github."""

    name = 'github'
    log = logging.getLogger("zuul.reporter.github.Reporter")

    def __init__(self, reporter_config={}, sched=None, connection=None):
        super(GithubReporter, self).__init__(
            reporter_config, sched, connection)
        self._github_status_value = None
        self._create_comment = False
        self._set_commit_status = False

    def postConfig(self):
        github_status_values = {
            self._action_start: 'pending',
            self._action_success: 'success',
            self._action_failure: 'failure',
            self._action_merge_failure: 'failure'
        }
        self._github_status_value = github_status_values[self._action]
        self._create_comment = self._shouldCreateComment()
        self._set_commit_status = self._shouldSetCommitStatus()

    def _shouldCreateComment(self):
        if self.reporter_config and 'comment' in self.reporter_config:
            return self.reporter_config['comment']

        # defaults to False on start action, True on any other action
        return self._action != self._action_start

    def _shouldSetCommitStatus(self):
        if self.reporter_config and 'commit_status' in self.reporter_config:
            return self.reporter_config.get('commit_status')
        return True

    def report(self, source, pipeline, item, message=None):
        """Comment on PR and set commit status."""
        if self._create_comment:
            self.addPullComment(pipeline, item, message)
        if (self._set_commit_status and
            hasattr(item.change, 'patchset') and
            item.change.patchset is not None):
            self.setPullStatus(pipeline, item)

    def addPullComment(self, pipeline, item, message):
        if message is None:
            message = self._formatItemReport(pipeline, item)
        owner, project = item.change.project.name.split('/')
        pr_number = item.change.number
        self.log.debug(
            'Reporting change %s, params %s, message: %s' %
            (item.change, self.reporter_config, message))
        self.connection.commentPull(owner, project, pr_number, message)

    def setPullStatus(self, pipeline, item):
        owner, project = item.change.project.name.split('/')
        sha = item.change.patchset
        context = pipeline.name
        state = self._github_status_value
        url = ''
        if self.sched.config.has_option('zuul', 'status_url'):
            url = self.sched.config.get('zuul', 'status_url')
        description = ''
        if pipeline.description:
            description = pipeline.description

        self.log.debug(
            'Reporting change %s, params %s, status:\n'
            'context: %s, state: %s, description: %s, url: %s' %
            (item.change, self.reporter_config, context, state,
             description, url))

        self.connection.setCommitStatus(
            owner, project, sha, state, url, description, context)


def getSchema():
    github_reporter = v.Any(
        v.Schema({'commit_status': bool,
                  'comment': bool}),
        None)
    return github_reporter
