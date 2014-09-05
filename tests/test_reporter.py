# Copyright 2014 Rackspace Australia
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
import testtools

import zuul.reporter

from tests.base import BaseAPIHelper


class TestSMTPReporter(testtools.TestCase, BaseAPIHelper):
    log = logging.getLogger("zuul.test_reporter")

    def setUp(self):
        super(TestSMTPReporter, self).setUp()

    def test_public_api_signatures(self):
        self.assertPublicAPISignatures(zuul.reporter.smtp.SMTPReporter,
                                       zuul.reporter.BaseReporter)

    def test_reporter_name(self):
        self.assertEqual('smtp', zuul.reporter.smtp.SMTPReporter.name)


class TestGerritReporter(testtools.TestCase, BaseAPIHelper):
    log = logging.getLogger("zuul.test_reporter")

    def setUp(self):
        super(TestGerritReporter, self).setUp()

    def test_public_api_signatures(self):
        self.assertPublicAPISignatures(zuul.reporter.gerrit.GerritReporter,
                                       zuul.reporter.BaseReporter)

    def test_reporter_name(self):
        self.assertEqual('gerrit', zuul.reporter.gerrit.GerritReporter.name)
