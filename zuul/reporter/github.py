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
    log = logging.getLogger("zuul.reporter.gerrit.Reporter")

    def __init__(self, reporter_config={}, sched=None, connection=None):
        super(GithubReporter, self).__init__(
            reporter_config, sched, connection)
        self._github_state = None

    def postConfig(self):
        github_states = {
            self._action_start: 'pending',
            self._action_success: 'success',
            self._action_failure: 'failure',
            self._action_merge_failure: 'failure'
        }
        self._github_state = github_states[self._action]
        self._create_comment = self._action != self._action_start

    def report(self, source, pipeline, item, message=None):
        """Comment on PR with test status."""
        if self._create_comment:
            self.addPullComment(pipeline, item, message)
        if (hasattr(item.change, 'patchset') and
            item.change.patchset is not None):
            self.setPullStatus(pipeline, item)

    def addPullComment(self, pipeline, item, message):
        if message is None:
            message = self._formatItemReport(pipeline, item)
        owner, project = item.change.project.name.split('/')
        pr_number = item.change.number
        self.connection.commentPull(owner, project, pr_number, message)

    def setPullStatus(self, pipeline, item):
        owner, project = item.change.project.name.split('/')
        sha = item.change.patchset
        context = pipeline.name
        state = self._github_state
        url = ''
        if self.sched.config.has_option('zuul', 'status_url'):
            url = self.sched.config.get('zuul', 'status_url')
        description = ''
        if pipeline.description:
            description = pipeline.description

        self.connection.setCommitStatus(
            owner, project, sha, state, url, description, context)


def getSchema():
    github_reporter = v.All()
    return github_reporter
