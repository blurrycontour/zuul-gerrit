# Copyright 2014 Antoine "hashar" Musso
# Copyright 2014 Wikimedia Foundation Inc.
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

import sys

import fixtures
import testtools

from zuul.cmd.cloner import Cloner

class ZuulCmdClonerTests(testtools.TestCase):

    common_opts = [
        '--zuul-url', 'zuul.example.com',
        '--zuul-project', 'example/project',
        '--zuul-pipeline', 'gate',
        '--zuul-commit', '1234EF',
        '--zuul-ref', 'refs/zuul/master/Z789AB',
    ]
    common_posargs = [
        'https://gerrit.example.com',
        'example/project',
    ]

    def test_change_params(self):
        parse = Cloner().parse_arguments(
            self.common_opts
            + [
                '--zuul-patchset', '1',
                '--zuul-branch', 'master',
                '--zuul-change', '12345',
            ]
            + self.common_posargs
        )

    def test_ref_params(self):
        Cloner().parse_arguments(
            self.common_opts
            + [
                '--zuul-oldrev', '1234',
                '--zuul-newrev', 'FEDC',
            ]
            + self.common_posargs
        )

    def test_missing_change_or_ref_params(self):

        stderr = self.useFixture(fixtures.StringStream('stderr')).stream
        self.useFixture(fixtures.MonkeyPatch('sys.stderr', stderr))

        self.assertRaises(SystemExit, Cloner().parse_arguments,
                          self.common_opts + self.common_posargs)

    def test_mixing_change_or_ref_params(self):

        stderr = self.useFixture(fixtures.StringStream('stderr')).stream
        self.useFixture(fixtures.MonkeyPatch('sys.stderr', stderr))

        self.assertRaises(SystemExit, Cloner().parse_arguments,
                          self.common_opts
                          + [
                              '--zuul-newrev', '777BCD',
                              '--zuul-change', '12345',
                          ]
                          + self.common_posargs)
