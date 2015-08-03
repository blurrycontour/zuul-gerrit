#!/usr/bin/env python

# Copyright 2015 BMW Car IT GmbH
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

try:
    from unittest import mock
except ImportError:
    import mock

from tests.base import ZuulTestCase, FakeChange
from zuul.trigger.gerrit import Gerrit


def build_query_results(num_fails, first_change=None, last_change=None):
    query_results = []
    if first_change:
        query_results.append(first_change.query())

    for i in range(num_fails):
        query_results.append({})

    if last_change:
        query_results.append(last_change.query())
    return query_results


class TestGerritTrigger(ZuulTestCase):

    def setUp(self):
        super(TestGerritTrigger, self).setUp()
        self.num_tries = self.config.getint('gerrit', 'query_attempts_max')

        self.change = FakeChange(self.fake_gerrit, 512, 'org/project',
                                 'master', 'A',
                                 upstream_root=self.upstream_root,
                                 status='NEW')
        self.change.patchset = 1

    @mock.patch('tests.base.FakeGerrit.query')
    def test_update_change_success(self, _query_mock):
        for i in range(self.num_tries):
            gerrit = Gerrit(self.config, self.sched)
            self.assertIsNotNone(gerrit)

            _query_mock.reset_mock()
            _query_mock.side_effect = build_query_results(i, None, self.change)

            updated_change = gerrit.updateChange(self.change)
            self.assertIsNotNone(updated_change)
            self.assertEqual(i + 1, _query_mock.call_count,
                             "Number of calls to query")

    @mock.patch('tests.base.FakeGerrit.query')
    def test_update_change_no_success(self, _query_mock):
        gerrit = Gerrit(self.config, self.sched)
        self.assertIsNotNone(gerrit)

        _query_mock.side_effect = build_query_results(
            self.num_tries, None, self.change)

        self.assertRaises(Exception, gerrit.updateChange, self.change)
        self.assertEqual(self.num_tries, _query_mock.call_count,
                         "Number of calls to query")

    @mock.patch('tests.base.FakeGerrit.query')
    def test_update_change_needed_by_success(self, _query_mock):
        change = FakeChange(self.fake_gerrit, 511, 'org/project', 'master',
                            'Needed by A', upstream_root=self.upstream_root,
                            status='NEW')
        change.patchset = 1
        change.setDependsOn(self.change, 1)

        for i in range(self.num_tries):
            _query_mock.reset_mock()
            _query_mock.side_effect = build_query_results(
                i, change, self.change)

            gerrit = Gerrit(self.config, self.sched)
            self.assertIsNotNone(gerrit)

            updated_change = gerrit.updateChange(change)
            self.assertIsNotNone(updated_change)

    @mock.patch('tests.base.FakeGerrit.query')
    def test_update_change_needed_by_no_success(self, _query_mock):
        change = FakeChange(self.fake_gerrit, 511, 'org/project', 'master',
                            'Needed by A', upstream_root=self.upstream_root,
                            status='NEW')
        change.patchset = 1
        change.setDependsOn(self.change, 1)

        _query_mock.reset_mock()
        _query_mock.side_effect = build_query_results(
            self.num_tries, change, self.change)

        gerrit = Gerrit(self.config, self.sched)
        self.assertIsNotNone(gerrit)

        self.assertRaises(Exception, gerrit.updateChange, self.change)
        self.assertEqual(self.num_tries + 1, _query_mock.call_count,
                         "Number of calls to query")
