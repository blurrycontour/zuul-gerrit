# Copyright 2015 Red Hat, Inc.
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

import zuul.model

from tests.base import BaseTestCase


class TestSkipIfOnlyRule(BaseTestCase):

    @property
    def rule(self):
        return zuul.model.SkipIfOnlyRule('project',
                                         ['^/COMMIT_MSG$', '^docs/.*$'])

    def _test_matches(self, skip_expected, files=None, project_name='project'):
        change = zuul.model.Change(project_name)
        change.files = files
        self.assertEqual(skip_expected, self.rule.matches(change))

    def test_str(self):
        self.assertEqual(str(self.rule),
                         '{SkipIfOnly[project]:^/COMMIT_MSG$^docs/.*$}')

    def test_repr(self):
        self.assertEqual(repr(self.rule), '<SkipIfOnlyRule project>')

    def test_matches_returns_false_when_no_files(self):
        self._test_matches(False, files=None)

    def test_matches_returns_false_when_project_does_not_match(self):
        self._test_matches(False, project_name=None)

    def test_matches_returns_false_when_some_files_match(self):
        self._test_matches(False, files=['/COMMIT_MSG', 'foo/bar'])

    def test_matches_returns_true_when_all_files_match(self):
        self._test_matches(True, files=['/COMMIT_MSG', 'docs/foo/bar'])


class TestJob(BaseTestCase):

    @property
    def job(self):
        job = zuul.model.Job('job')
        rule = zuul.model.SkipIfOnlyRule('project', ['^/COMMIT_MSG$'])
        job.skip_if_only_rules.append(rule)
        return job

    def test_change_matches_returns_false_for_matched_skip_if_only_rule(self):
        job = self.job
        rule = job.skip_if_only_rules[0]
        change = zuul.model.Change(rule.project_name)
        change.files = ['/COMMIT_MSG']
        self.assertFalse(job.changeMatches(change))

    def test_copy_retains_skip_if_only_rules(self):
        job = zuul.model.Job('job')
        job.copy(self.job)
        self.assertTrue(job.skip_if_only_rules)
