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

import asyncio
import functools
import logging
import json
import os
import os.path
import socket
import tempfile
import threading
import time

from autobahn.asyncio.websocket import WebSocketClientFactory
from autobahn.asyncio.websocket import WebSocketClientProtocol

import zuul.streamer
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


class WSClientProtocol(WebSocketClientProtocol):
    def __init__(self, build_uuid, results, event):
        super(WebSocketClientProtocol, self).__init__()
        self.build_uuid = build_uuid
        self.event = event
        self.results = results

    def onOpen(self):
        data = {'uuid': self.build_uuid, 'logfile': None}
        msg = json.dumps(data)
        self.sendMessage(msg.encode('utf8'))

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("WSClientProtocol not expecting binary")
            self.sendClose()
        self.results += payload.decode('utf8')
        # Let the test know we've connected and begun communication
        self.event.set()

    def onClose(self, wasClean, code, reason):
        print("Websocket connection closed: code=%s, reason=%s" %
              (code, reason))
        print("Websocket results: %s" % self.results)
        self.factory.loop.stop()
        self.event.set()


class TestStreaming(tests.base.AnsibleZuulTestCase):

    tenant_config_file = 'config/streamer/main.yaml'
    log = logging.getLogger("zuul.test.test_log_streamer.TestStreaming")

    def setUp(self):
        super(TestStreaming, self).setUp()
        self.host = '0.0.0.0'
        self.streamer = None
        self.stop_streamer = False
        self.streaming_data = ''
        self.test_streaming_event = threading.Event()

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
        self.test_streaming_event.set()

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

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        while not os.path.exists(build_dir):
            time.sleep(0.1)

        # Need to wait to make sure that jobdir gets set
        while build.jobdir is None:
            time.sleep(0.1)
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        while not os.path.exists(ansible_log):
            time.sleep(0.1)
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Create a thread to stream the log. We need this to be happening
        # before we create the flag file to tell the job to complete.
        port = 7901
        streamer_thread = threading.Thread(
            target=self.startStreamer,
            args=(port, build.uuid, self.executor_server.jobdir_root,)
        )
        streamer_thread.start()
        self.addCleanup(self.stopStreamer)
        self.test_streaming_event.wait()

        # Allow the job to complete, which should close the streaming
        # connection (and terminate the thread) as well since the log file
        # gets closed/deleted.
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()
        self.waitUntilSettled()
        streamer_thread.join()

        # Now that the job is finished, the log file has been closed by the
        # job and deleted. However, we still have a file handle to it, so we
        # can make sure that we read the entire contents at this point.
        # Compact the returned lines into a single string for easy comparison.
        file_contents = ''.join(logfile.readlines())
        logfile.close()

        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n", self.streaming_data)
        self.assertEqual(file_contents, self.streaming_data)

    def startWSClient(self, host, port, build_uuid, results, event):
        # We expect to be started in a new thread, so create a separate
        # event loop for it.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        factory = WebSocketClientFactory(u"ws://%s:%s" % (host, port))
        factory.protocol = functools.partial(
            WSClientProtocol, build_uuid, results, event)
        coro = loop.create_connection(factory, host, port)
        loop.run_until_complete(coro)
        loop.run_forever()
        loop.close()

    def test_websocket_streaming(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        while not len(self.builds):
            time.sleep(0.1)
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        while not os.path.exists(build_dir):
            time.sleep(0.1)

        # Need to wait to make sure that jobdir gets set
        while build.jobdir is None:
            time.sleep(0.1)
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        while not os.path.exists(ansible_log):
            time.sleep(0.1)
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Start the finger streamer daemon
        port = 7902
        streamer = zuul.lib.log_streamer.LogStreamer(
            None, self.host, port, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)

        # Start the websocket streamer
        ws_streamer = zuul.streamer.ZuulStreamer()
        loop = asyncio.new_event_loop()
        ws_streamer_thread = threading.Thread(
            target=ws_streamer.run, args=(loop,))
        ws_streamer_thread.start()
        self.addCleanup(ws_streamer.stop)

        # FIXME: Wait until websocket streamer is started
        time.sleep(2)

        # Start a thread with the websocket client
        results = ''
        ws_event = threading.Event()
        ws_client_thread = threading.Thread(
            target=self.startWSClient,
            args=(self.host, port, build.uuid, results, ws_event,)
        )
        ws_client_thread.start()

        # Wait until the client has begun receiving data, or terminated
        ws_event.wait()

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()
        self.waitUntilSettled()
        ws_client_thread.join()

        file_contents = ''.join(logfile.readlines())
        logfile.close()
        self.assertEqual(file_contents, results)
