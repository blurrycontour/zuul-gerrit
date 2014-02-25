#!/usr/bin/env python

# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

import ConfigParser
import logging
import os

import tests.test_scheduler

FIXTURE_DIR = os.path.join(os.path.dirname(__file__),
                           'fixtures')
CONFIG = ConfigParser.ConfigParser()
CONFIG.read(os.path.join(FIXTURE_DIR, "zuul_remote.conf"))

CONFIG.set('zuul', 'layout_config',
           os.path.join(FIXTURE_DIR, "layout.yaml"))

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-32s '
                    '%(levelname)-8s %(message)s')


class TestSchedulerRemote(tests.test_scheduler.TestScheduler):
    log = logging.getLogger("zuul.test")

    TEST_CONFIG = CONFIG

    def setUp(self):
        self.make_dirs()
        # Preset config values.
        self.TEST_CONFIG.set('merger', 'poll', 'True')
        self.TEST_CONFIG.set('gerrit', 'fetch_url', self.upstream_root)
        super(TestSchedulerRemote, self).setUp()
