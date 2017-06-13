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
import tempfile
import threading
import time

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
        self.streamer = None
        self.stop_streamer = False
        self.streaming_data = ''

    def stopStreamer(self):
        self.stop_streamer = True

    def startStreamer(self, port, build_uuid, root=None):
        if not root:
            root = tempfile.gettempdir()
        self.streamer = zuul.lib.log_streamer.LogStreamer(None, self.host,
                                                          port, root)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.host, port))
        self.addCleanup(s.close)

        req = '%s\n' % build_uuid
        s.sendall(req.encode('utf-8'))

        while not self.stop_streamer:
            data = s.recv(2048)
            if not data:
                break
            self.streaming_data += data.decode('utf-8')

        s.shutdown(socket.SHUT_RDWR)
        s.close()
        self.streamer.stop()

    def test_streaming(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        while not len(self.builds):
            time.sleep(0.1)
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        # Job should be waiting for the flag file at the start.
        # Might need to wait for the build dir to be created before we can
        # create the flag file.
        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        flag_file = os.path.join(build_dir, 'test_wait')
        while not os.path.exists(build_dir):
            time.sleep(0.1)
        open(flag_file, 'w').close()

        # Need to wait to make sure that jobdir gets set
        while build.jobdir is None:
            time.sleep(0.1)
            build = self.builds[0]

        # We can now safely access the ansible log. We only open it (to
        # force a file handle to be kept open for it after the job finishes)
        # but wait to read the contents until the job is done. We also have
        # another sync point here to wait until the log file actually exists.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        while not os.path.exists(ansible_log):
            time.sleep(0.1)
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Create a thread to stream the log. We need this to be happening
        # while we create the flag file to tell the job to complete.
        port = 7901
        streamer_thread = threading.Thread(
            target=self.startStreamer,
            args=(port, build.uuid, self.executor_server.jobdir_root,)
        )
        streamer_thread.start()
        self.addCleanup(self.stopStreamer)

        # Allow the job to complete, which should close the streaming
        # connection (and terminate the thread) as well since the log file
        # gets closed/deleted.
        open(flag_file, 'w').close()
        self.waitUntilSettled()
        streamer_thread.join()

        # Now that the job is finished, the log file has been closed by the
        # job and deleted. However, we still have a file handle to it, so we
        # can make sure that we read the entire contents at this point.
        file_contents = logfile.readlines()
        logfile.close()

        # Compact the returned lines into a single string for easy comparison.
        orig = ''.join(file_contents)
        self.log.debug("\n\nFile contents: %s\n\n", orig)
        self.log.debug("\n\nStreamed: %s\n\n", self.streaming_data)
        self.assertEqual(orig, self.streaming_data)
