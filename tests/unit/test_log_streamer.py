#!/usr/bin/env python

# Copyright 2017 Red Hat, Inc.
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

import os
import os.path
import socket
import sys
import tempfile

from unittest import skipIf

import zuul.lib.log_streamer
import tests.base


class TestLogStreamer(tests.base.BaseTestCase):

    def setUp(self):
        super(TestLogStreamer, self).setUp()
        self.host = '0.0.0.0'

    def startStreamer(self, port, root=None):
        if not root:
            root = tempfile.gettempdir()
        return zuul.lib.log_streamer.LogStreamer(None, self.host, port, root)

    def test_start_stop(self):
        port = 7900
        streamer = self.startStreamer(port)
        self.addCleanup(streamer.stop)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        self.assertEqual(0, s.connect_ex((self.host, port)))
        s.close()

        streamer.stop()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        self.assertNotEqual(0, s.connect_ex((self.host, port)))
        s.close()


class TestStreaming(tests.base.AnsibleZuulTestCase):

    tenant_config_file = 'config/streamer/main.yaml'

    def setUp(self):
        super(TestStreaming, self).setUp()
        self.host = '0.0.0.0'

    def startStreamer(self, port, root=None):
        if not root:
            root = tempfile.gettempdir()
        return zuul.lib.log_streamer.LogStreamer(None, self.host, port, root)

    @skipIf(sys.version_info.major != 3 or sys.version_info.minor < 5,
            'Python 3.5 or greater required')
    def test_streaming(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # this hangs with wait_for in the playbook
        self.waitUntilSettled()

        self.log.debug("******* DWS executor.jobdir_root: %s",
                       self.executor_server.jobdir_root)
        self.log.debug("******* DWS builds: %s", self.builds)

        build = None
        for b in self.builds:
            if b.name == 'python27':
                build = b
                break
        self.assertIsNotNone(build)

        self.log.debug("******* DWS build.jobdir.log_root: %s",
                       build.jobdir.log_root)

        ansible_log = os.path.join(build.jobdir.log_root, 'ansible_log.txt')
        self.assertTrue(os.path.exists(ansible_log))

        # Start the finger log streamer
        port = 7901
        streamer = self.startStreamer(port)
        self.addCleanup(streamer.stop)
