# Copyright 2015 Red Hat, Inc.
# Copyright 2023 Acme Gating, LLC
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

from zuul import change_matcher as cm
from zuul import model
from zuul.lib.re2util import ZuulRegex

from tests.base import BaseTestCase


class BaseTestMatcher(BaseTestCase):

    project = 'project'

    def setUp(self):
        super(BaseTestMatcher, self).setUp()
        self.change = model.Change(self.project)


class TestAbstractChangeMatcher(BaseTestMatcher):

    def test_str(self):
        matcher = cm.ProjectMatcher(ZuulRegex(self.project))
        self.assertEqual(str(matcher), '{ProjectMatcher:project}')

    def test_repr(self):
        matcher = cm.ProjectMatcher(ZuulRegex(self.project))
        self.assertEqual(repr(matcher), '<ProjectMatcher project>')


class TestProjectMatcher(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = cm.ProjectMatcher(ZuulRegex(self.project))
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false(self):
        matcher = cm.ProjectMatcher(ZuulRegex('not_project'))
        self.assertFalse(matcher.matches(self.change))


class TestBranchMatcher(BaseTestMatcher):

    def setUp(self):
        super(TestBranchMatcher, self).setUp()
        self.matcher = cm.BranchMatcher(ZuulRegex('foo'))

    def test_matches_returns_true_on_matching_branch(self):
        self.change.branch = 'foo'
        self.assertTrue(self.matcher.matches(self.change))

    def test_matches_returns_true_on_matching_ref(self):
        delattr(self.change, 'branch')
        self.change.ref = 'foo'
        self.assertTrue(self.matcher.matches(self.change))

    def test_matches_returns_false_for_no_match(self):
        self.change.branch = 'bar'
        self.change.ref = 'baz'
        self.assertFalse(self.matcher.matches(self.change))

    def test_containing_branch_partial_match(self):
        self.change = model.Tag(self.project)
        self.change.ref = 'refs/tags/1.0'
        self.matcher = cm.BranchMatcher(ZuulRegex('^release-'))
        self.change.containing_branches = ["release-1.0", "master"]
        self.assertTrue(self.matcher.matches(self.change))


class TestAbstractMatcherCollection(BaseTestMatcher):

    def test_str(self):
        matcher = cm.MatchAll([cm.FileMatcher(ZuulRegex('foo'))])
        self.assertEqual(str(matcher), '{MatchAll:{FileMatcher:foo}}')

    def test_repr(self):
        matcher = cm.MatchAll([])
        self.assertEqual(repr(matcher), '<MatchAll []>')


class BaseTestFilesMatcher(BaseTestMatcher):

    def _test_matches(self, expected, files=None):
        if files is not None:
            self.change.files = files
        self.assertEqual(expected, self.matcher.matches(self.change))


class TestMatchAllFiles(BaseTestFilesMatcher):

    def setUp(self):
        super(TestMatchAllFiles, self).setUp()
        self.matcher = cm.MatchAllFiles(
            [cm.FileMatcher(ZuulRegex('^docs/.*$'))])

    def test_matches_returns_false_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self._test_matches(False)

    def test_matches_returns_false_when_no_files(self):
        self._test_matches(False)

    def test_matches_returns_false_when_not_all_files_match(self):
        self._test_matches(False, files=['/COMMIT_MSG', 'docs/foo', 'foo/bar'])

    def test_matches_returns_true_when_single_file_does_not_match(self):
        self._test_matches(True, files=['docs/foo'])

    def test_matches_returns_false_when_commit_message_matches(self):
        self._test_matches(False, files=['/COMMIT_MSG'])

    def test_matches_returns_true_when_all_files_match(self):
        self._test_matches(True, files=['/COMMIT_MSG', 'docs/foo'])

    def test_matches_returns_true_when_single_file_matches(self):
        self._test_matches(True, files=['docs/foo'])


class TestMatchAllFilesNegate(BaseTestFilesMatcher):

    def setUp(self):
        super().setUp()
        self.matcher = cm.MatchAllFiles(
            [cm.FileMatcher(ZuulRegex('^docs/.*$', negate=True))])

    def test_matches_returns_false_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self._test_matches(False)

    def test_matches_returns_false_when_no_files(self):
        self._test_matches(False)

    def test_matches_returns_false_when_not_all_files_match(self):
        self._test_matches(False, files=['/COMMIT_MSG', 'docs/foo', 'foo/bar'])

    def test_matches_returns_false_when_single_file_does_not_match(self):
        self._test_matches(False, files=['docs/foo'])

    def test_matches_returns_false_when_commit_message_matches(self):
        self._test_matches(False, files=['/COMMIT_MSG'])

    def test_matches_returns_false_when_all_files_match(self):
        self._test_matches(False, files=['/COMMIT_MSG', 'docs/foo'])

    def test_matches_returns_false_when_single_file_matches(self):
        self._test_matches(False, files=['docs/foo'])

    def test_matches_returns_true_when_no_files_match(self):
        self._test_matches(True, files=['foo'])


class TestMatchAnyFiles(BaseTestFilesMatcher):

    def setUp(self):
        super(TestMatchAnyFiles, self).setUp()
        self.matcher = cm.MatchAnyFiles(
            [cm.FileMatcher(ZuulRegex('^docs/.*$'))])

    def test_matches_returns_true_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self._test_matches(True)

    def test_matches_returns_true_when_no_files(self):
        self._test_matches(True)

    def test_matches_returns_true_when_only_commit_message(self):
        self._test_matches(True, files=['/COMMIT_MSG'])

    def test_matches_returns_true_when_some_files_match(self):
        self._test_matches(True, files=['/COMMIT_MSG', 'docs/foo', 'foo/bar'])

    def test_matches_returns_true_when_single_file_matches(self):
        self._test_matches(True, files=['docs/foo'])

    def test_matches_returns_false_when_no_matching_files(self):
        self._test_matches(False, files=['/COMMIT_MSG', 'foo/bar'])


class TestMatchAnyFilesNegate(BaseTestFilesMatcher):

    def setUp(self):
        super().setUp()
        self.matcher = cm.MatchAnyFiles(
            [cm.FileMatcher(ZuulRegex('^docs/.*$', negate=True))])

    def test_matches_returns_true_when_files_attr_missing(self):
        delattr(self.change, 'files')
        self._test_matches(True)

    def test_matches_returns_true_when_no_files(self):
        self._test_matches(True)

    def test_matches_returns_true_when_only_commit_message(self):
        self._test_matches(True, files=['/COMMIT_MSG'])

    def test_matches_returns_true_when_some_files_match(self):
        self._test_matches(True, files=['/COMMIT_MSG', 'docs/foo', 'foo/bar'])

    def test_matches_returns_false_when_single_file_matches(self):
        self._test_matches(False, files=['docs/foo'])

    def test_matches_returns_true_when_no_matching_files(self):
        self._test_matches(True, files=['/COMMIT_MSG', 'foo/bar'])


class TestMatchAll(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = cm.MatchAll([cm.ProjectMatcher(ZuulRegex(self.project))])
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false_for_missing_matcher(self):
        matcher = cm.MatchAll([cm.ProjectMatcher(ZuulRegex('not_project'))])
        self.assertFalse(matcher.matches(self.change))


class TestMatchAny(BaseTestMatcher):

    def test_matches_returns_true(self):
        matcher = cm.MatchAny([cm.ProjectMatcher(ZuulRegex(self.project))])
        self.assertTrue(matcher.matches(self.change))

    def test_matches_returns_false(self):
        matcher = cm.MatchAny([cm.ProjectMatcher(ZuulRegex('not_project'))])
        self.assertFalse(matcher.matches(self.change))
