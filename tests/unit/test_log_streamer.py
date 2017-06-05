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
import time

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
        streamer = zuul.lib.log_streamer.LogStreamer(None, self.host,
                                                     port, root)
        self.addCleanup(streamer.stop)
        return streamer

    @skipIf(sys.version_info.major != 3 or sys.version_info.minor < 5,
            'Python 3.5 or greater required')
    def test_streaming(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        while not len(self.builds):
            time.sleep(0.1)
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        # Job should be waiting for the flag file at the start
        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        flag_file = os.path.join(build_dir, 'test_wait')

        # Might need to wait for the build dir to be created
        while not os.path.exists(build_dir):
            time.sleep(0.1)
        open(flag_file, 'w').close()

        # When the flag file disappears, the job should be done, but waiting
        # for the flag file to reappear. We need it to not be completely
        # finished so we can get to the log file.
        delete_me_when_i_work = 10
        while os.path.exists(flag_file):
            # We are now getting stuck here because the job doesn't seem to run
            self.log.debug("%s exists", flag_file)
            time.sleep(1)
            delete_me_when_i_work -= 1
            if delete_me_when_i_work == 0:
                break

        # We can now safely access the ansible log
        ansible_log = os.path.join(build.jobdir.log_root, 'ansible_log.txt')
        self.assertTrue(os.path.exists(ansible_log))
        with open(ansible_log, 'r') as logfile:
            contents = logfile.readlines()
        self.log.debug("\n\nContents: %s\n\n", contents)


        # Abort here until we figure out how to compare log output
        self.assertTrue(False)


        port = 7901
        streamer = self.startStreamer(port, self.executor_server.jobdir_root)

        returned_content = ''
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, port))
        req = '%s' % build.uuid
        s.sendall(req.encode('utf-8'))

        # TODO(Shrews): Figure out how to break the connection
        while True:
            data = s.recv(1024).decode('utf-8')
            if not data:
                break
            returned_content += data
            self.log.debug("\n\nReturned: %s\n\n", returned_content)

        # Allow the job to complete
        open(flag_file, 'w').close()
        self.waitUntilSettled()
