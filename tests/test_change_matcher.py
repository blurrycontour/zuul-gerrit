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

from zuul import change_matcher
from zuul import model

from tests.base import BaseTestCase


class BaseTestMatcher(BaseTestCase):

    project = 'project'

    def setUp(self):
        super(BaseTestMatcher, self).setUp()
        self.change = model.Change(self.project)


class TestAbstractChangeMatcher(BaseTestMatcher):

    def test_str(self):
        matcher = change_matcher.ProjectMatcher(self.project)
        self.assertEqual(str(matcher), '{ProjectMatcher:project}')

    def test_repr(self):
        matcher = change_matcher.ProjectMatcher(self.project)
        self.assertEqual(repr(matcher), '<ProjectMatcher project>')


class TestProjectMatcher(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = change_matcher.ProjectMatcher(self.project)
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false(self):
        matcher = change_matcher.ProjectMatcher('not_project')
        self.assertFalse(matcher.matches(self.change))


class TestFileMatcher(BaseTestMatcher):

    def setUp(self):
        super(TestFileMatcher, self).setUp()
        self.matcher = change_matcher.FileMatcher('filename')

    def test_matches_returns_true(self):
        self.change.files = ['filename']
        self.assertTrue(self.matcher.matches(self.change))

    def test_matches_returns_false_when_no_files(self):
        self.assertFalse(self.matcher.matches(self.change))

    def test_matches_returns_false_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self.assertFalse(self.matcher.matches(self.change))


class TestMatchAllFiles(BaseTestMatcher):

    def setUp(self):
        super(TestMatchAllFiles, self).setUp()
        cm = change_matcher
        self.matcher = cm.MatchAllFiles([cm.FileMatcher('^docs/.*$')])

    def _test_matches(self, expected, files=None):
        if files is not None:
            self.change.files = files
        self.assertEqual(expected, self.matcher.matches(self.change))

    def test_matches_returns_false_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self._test_matches(False)

    def test_matches_returns_false_when_no_files(self):
        self._test_matches(False)

    def test_matches_returns_false_when_not_all_files_match(self):
        self._test_matches(False, files=['foo/bar'])

    def test_matches_returns_true_when_commit_message_matches(self):
        self._test_matches(True, files=['/COMMIT_MSG'])

    def test_matches_returns_true_when_all_files_match(self):
        self._test_matches(True, files=['docs/foo'])


class TestMatchOnAll(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = change_matcher.MatchOnAll(
            [change_matcher.ProjectMatcher(self.project)])
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false_for_missing_matcher(self):
        matcher = change_matcher.MatchOnAll(
            [change_matcher.ProjectMatcher('not_project')])
        self.assertFalse(matcher.matches(self.change))


class TestMatchOnAny(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = change_matcher.MatchOnAny(
            [change_matcher.ProjectMatcher(self.project)])
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false(self):
        matcher = change_matcher.MatchOnAny(
            [change_matcher.ProjectMatcher('not_project')])
        self.assertFalse(matcher.matches(self.change))
