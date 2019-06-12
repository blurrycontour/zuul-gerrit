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
import configparser
import io
import logging
import json
import os
import os.path
import re
import socket
import tempfile
import testtools
import threading
import time

import zuul.web
import zuul.lib.log_streamer
from zuul.lib.fingergw import FingerGateway
import tests.base
from tests.base import iterate_timeout, ZuulWebFixture

from ws4py.client import WebSocketBaseClient

from zuul.lib.gear_utils import getGearmanFunctions


class WSClient(WebSocketBaseClient):
    def __init__(self, port, build_uuid):
        self.port = port
        self.build_uuid = build_uuid
        self.results = ''
        self.event = threading.Event()
        uri = 'ws://[::1]:%s/api/tenant/tenant-one/console-stream' % port
        super(WSClient, self).__init__(uri)

        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def received_message(self, message):
        if message.is_text:
            self.results += message.data.decode('utf-8')

    def run(self):
        self.connect()
        req = {'uuid': self.build_uuid, 'logfile': None}
        self.send(json.dumps(req))
        self.event.set()
        super(WSClient, self).run()
        self.close()


class TestLogStreamer(tests.base.BaseTestCase):

    def startStreamer(self, host, port, root=None):
        self.host = host
        if not root:
            root = tempfile.gettempdir()
        return zuul.lib.log_streamer.LogStreamer(self.host, port, root)

    def test_start_stop_ipv6(self):
        streamer = self.startStreamer('::1', 0)
        self.addCleanup(streamer.stop)

        port = streamer.server.socket.getsockname()[1]
        s = socket.create_connection((self.host, port))
        s.close()

        streamer.stop()

        with testtools.ExpectedException(ConnectionRefusedError):
            s = socket.create_connection((self.host, port))
        s.close()

    def test_start_stop_ipv4(self):
        streamer = self.startStreamer('127.0.0.1', 0)
        self.addCleanup(streamer.stop)

        port = streamer.server.socket.getsockname()[1]
        s = socket.create_connection((self.host, port))
        s.close()

        streamer.stop()

        with testtools.ExpectedException(ConnectionRefusedError):
            s = socket.create_connection((self.host, port))
        s.close()


class TestStreamingBase(tests.base.AnsibleZuulTestCase):

    tenant_config_file = 'config/streamer/main.yaml'
    log = logging.getLogger("zuul.test_streaming")

    def setUp(self):
        super().setUp()
        self.host = '::'
        self.streamer = None
        self.stop_streamer = False
        self.streaming_data = {}
        self.test_streaming_event = threading.Event()

    def stopStreamer(self):
        self.stop_streamer = True

    def startStreamer(self, port, build_uuid, root=None):
        if not root:
            root = tempfile.gettempdir()
        self.streamer = zuul.lib.log_streamer.LogStreamer(self.host,
                                                          port, root)
        port = self.streamer.server.socket.getsockname()[1]
        s = socket.create_connection((self.host, port))
        self.addCleanup(s.close)

        req = '%s\r\n' % build_uuid
        s.sendall(req.encode('utf-8'))
        self.test_streaming_event.set()

        self.streaming_data.setdefault(None, '')
        while not self.stop_streamer:
            data = s.recv(2048)
            if not data:
                break
            self.streaming_data[None] += data.decode('utf-8')

        s.shutdown(socket.SHUT_RDWR)
        s.close()
        self.streamer.stop()

    def runFingerClient(self, build_uuid, gateway_address, event, name=None):
        # Wait until the gateway is started
        for x in iterate_timeout(30, "finger client to start"):
            try:
                # NOTE(Shrews): This causes the gateway to begin to handle
                # a request for which it never receives data, and thus
                # causes the getCommand() method to timeout (seen in the
                # test results, but is harmless).
                with socket.create_connection(gateway_address) as s:
                    break
            except ConnectionRefusedError:
                pass

        self.streaming_data[name] = ''
        with socket.create_connection(gateway_address) as s:
            msg = "%s\r\n" % build_uuid
            s.sendall(msg.encode('utf-8'))
            event.set()  # notify we are connected and req sent
            while True:
                data = s.recv(1024)
                if not data:
                    break
                self.streaming_data[name] += data.decode('utf-8')
            s.shutdown(socket.SHUT_RDWR)

    def runFingerGateway(self, zone=None):
        self.log.info('Starting fingergw with zone %s', zone)
        config = configparser.ConfigParser()
        config.read_dict({
            'gearman': {
                'server': '127.0.0.1',
                'port': str(self.gearman_server.port),
            },
            'fingergw': {
                'listen_address': self.host,
                'port': '0',
                'hostname': 'localhost',
            }
        })
        if zone:
            config.set('fingergw', 'zone', zone)

        gateway = FingerGateway(
            self.config,
            command_socket=None,
            pid_file=None
        )
        gateway.history = []
        gateway.start()
        self.addCleanup(gateway.stop)

        if zone:
            for _ in iterate_timeout(20, 'fingergw is registered'):
                functions = getGearmanFunctions(gateway.gearworker.gearman)
                jobname = 'fingergw:info:%s' % zone
                if jobname in functions:
                    break

        gateway_port = gateway.server.socket.getsockname()[1]
        return self.host, gateway_port


class TestStreaming(TestStreamingBase):

    def test_streaming(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "builds"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Create a thread to stream the log. We need this to be happening
        # before we create the flag file to tell the job to complete.
        streamer_thread = threading.Thread(
            target=self.startStreamer,
            args=(0, build.uuid, self.executor_server.jobdir_root,)
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
        file_contents = logfile.read()
        logfile.close()

        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n", self.streaming_data[None])
        self.assertEqual(file_contents, self.streaming_data[None])

        # Check that we logged a multiline debug message
        pattern = (r'^\d\d\d\d-\d\d-\d\d \d\d:\d\d\:\d\d\.\d\d\d\d\d\d \| '
                   r'Debug Test Token String$')
        r = re.compile(pattern, re.MULTILINE)
        match = r.search(self.streaming_data[None])
        self.assertNotEqual(match, None)

    def runWSClient(self, port, build_uuid):
        client = WSClient(port, build_uuid)
        client.event.wait()
        return client

    def test_decode_boundaries(self):
        '''
        Test multi-byte characters crossing read buffer boundaries.

        The finger client used by ZuulWeb reads in increments of 1024 bytes.
        If the last byte is a multi-byte character, we end up with an error
        similar to:

           'utf-8' codec can't decode byte 0xe2 in position 1023: \
           unexpected end of data

        By making the 1024th character in the log file a multi-byte character
        (here, the Euro character), we can test this.
        '''
        # Start the web server
        web = self.useFixture(
            ZuulWebFixture(self.changes, self.config,
                           self.additional_event_queues, self.upstream_root,
                           self.rpcclient, self.poller_events,
                           self.git_url_with_auth, self.addCleanup,
                           self.test_root))

        # Start the finger streamer daemon
        streamer = zuul.lib.log_streamer.LogStreamer(
            self.host, 0, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)

        # Need to set the streaming port before submitting the job
        finger_port = streamer.server.socket.getsockname()[1]
        self.executor_server.log_streaming_port = finger_port

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "builds"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break

        # Replace log file contents with the 1024th character being a
        # multi-byte character.
        with io.open(ansible_log, 'w', encoding='utf8') as f:
            f.write("a" * 1023)
            f.write(u"\u20AC")

        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Start a thread with the websocket client
        client1 = self.runWSClient(web.port, build.uuid)
        client1.event.wait()

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()

        # Wait for the websocket client to complete, which it should when
        # it's received the full log.
        client1.thread.join()

        self.waitUntilSettled()

        file_contents = logfile.read()
        logfile.close()
        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n", client1.results)
        self.assertEqual(file_contents, client1.results)

    def test_websocket_streaming(self):
        # Start the web server
        web = self.useFixture(
            ZuulWebFixture(self.changes, self.config,
                           self.additional_event_queues, self.upstream_root,
                           self.rpcclient, self.poller_events,
                           self.git_url_with_auth, self.addCleanup,
                           self.test_root))

        # Start the finger streamer daemon
        streamer = zuul.lib.log_streamer.LogStreamer(
            self.host, 0, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)

        # Need to set the streaming port before submitting the job
        finger_port = streamer.server.socket.getsockname()[1]
        self.executor_server.log_streaming_port = finger_port

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "build"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Start a thread with the websocket client
        client1 = self.runWSClient(web.port, build.uuid)
        client1.event.wait()
        client2 = self.runWSClient(web.port, build.uuid)
        client2.event.wait()

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()

        # Wait for the websocket client to complete, which it should when
        # it's received the full log.
        client1.thread.join()
        client2.thread.join()

        self.waitUntilSettled()

        file_contents = logfile.read()
        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n", client1.results)
        self.assertEqual(file_contents, client1.results)
        self.log.debug("\n\nStreamed: %s\n\n", client2.results)
        self.assertEqual(file_contents, client2.results)

    def test_websocket_hangup(self):
        # Start the web server
        web = self.useFixture(
            ZuulWebFixture(self.changes, self.config,
                           self.additional_event_queues, self.upstream_root,
                           self.rpcclient, self.poller_events,
                           self.git_url_with_auth, self.addCleanup,
                           self.test_root))

        # Start the finger streamer daemon
        streamer = zuul.lib.log_streamer.LogStreamer(
            self.host, 0, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)

        # Need to set the streaming port before submitting the job
        finger_port = streamer.server.socket.getsockname()[1]
        self.executor_server.log_streaming_port = finger_port

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "build"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break
            build = self.builds[0]

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break

        # Start a thread with the websocket client
        client1 = self.runWSClient(web.port, build.uuid)
        client1.event.wait()

        # Wait until we've streamed everything so far
        for x in iterate_timeout(30, "streamer is caught up"):
            with open(ansible_log, 'r') as logfile:
                if client1.results == logfile.read():
                    break
            # This is intensive, give it some time
            time.sleep(1)
        self.assertNotEqual(len(web.web.stream_manager.streamers.keys()), 0)

        # Hangup the client side
        client1.close(1000, 'test close')
        client1.thread.join()

        # The client should be de-registered shortly
        for x in iterate_timeout(30, "client cleanup"):
            if len(web.web.stream_manager.streamers.keys()) == 0:
                break

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()

        self.waitUntilSettled()

    def test_finger_gateway(self):
        # Start the finger streamer daemon
        streamer = zuul.lib.log_streamer.LogStreamer(
            self.host, 0, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)
        finger_port = streamer.server.socket.getsockname()[1]

        # Need to set the streaming port before submitting the job
        self.executor_server.log_streaming_port = finger_port

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "build"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        # Start the finger gateway daemon
        _, gateway_address = self.runFingerGateway()

        # Start a thread with the finger client
        finger_client_event = threading.Event()
        self.finger_client_results = ''
        finger_client_thread = threading.Thread(
            target=self.runFingerClient,
            args=(build.uuid, gateway_address, finger_client_event)
        )
        finger_client_thread.start()
        finger_client_event.wait()

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()

        # Wait for the finger client to complete, which it should when
        # it's received the full log.
        finger_client_thread.join()

        self.waitUntilSettled()

        file_contents = logfile.read()
        logfile.close()
        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n", self.streaming_data[None])
        self.assertEqual(file_contents, self.streaming_data[None])


class CountingFingerRequestHandler(zuul.lib.fingergw.RequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # if not hasattr(self.fingergw, 'history'):
        #     self.fingergw.history = []

    def _fingerClient(self, server, port, build_uuid):
        self.fingergw.history.append(build_uuid)
        super()._fingerClient(server, port, build_uuid)


class TestStreamingZones(TestStreamingBase):

    def setUp(self):
        super().setUp()
        self.fake_nodepool.attributes = {'executor-zone': 'eu-central'}
        zuul.lib.fingergw.FingerGateway.handler_class = \
            CountingFingerRequestHandler

    def setup_config(self, config_file: str):
        config = super().setup_config(config_file)
        config.set('executor', 'zone', 'eu-central')
        return config

    def _run_finger_client(self, build, address, name):
        # Start a thread with the finger client
        finger_client_event = threading.Event()
        self.finger_client_results = ''
        finger_client_thread = threading.Thread(
            target=self.runFingerClient,
            args=(build.uuid, address, finger_client_event),
            kwargs={'name': name}
        )
        finger_client_thread.start()
        finger_client_event.wait()
        return finger_client_thread

    def test_finger_gateway(self):
        # Start the finger streamer daemon
        streamer = zuul.lib.log_streamer.LogStreamer(
            self.host, 0, self.executor_server.jobdir_root)
        self.addCleanup(streamer.stop)
        finger_port = streamer.server.socket.getsockname()[1]

        # Need to set the streaming port before submitting the job
        self.executor_server.log_streaming_port = finger_port

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        # We don't have any real synchronization for the ansible jobs, so
        # just wait until we get our running build.
        for x in iterate_timeout(30, "build"):
            if len(self.builds):
                break
        build = self.builds[0]
        self.assertEqual(build.name, 'python27')

        build_dir = os.path.join(self.executor_server.jobdir_root, build.uuid)
        for x in iterate_timeout(30, "build dir"):
            if os.path.exists(build_dir):
                break

        # Need to wait to make sure that jobdir gets set
        for x in iterate_timeout(30, "jobdir"):
            if build.jobdir is not None:
                break

        # Wait for the job to begin running and create the ansible log file.
        # The job waits to complete until the flag file exists, so we can
        # safely access the log here. We only open it (to force a file handle
        # to be kept open for it after the job finishes) but wait to read the
        # contents until the job is done.
        ansible_log = os.path.join(build.jobdir.log_root, 'job-output.txt')
        for x in iterate_timeout(30, "ansible log"):
            if os.path.exists(ansible_log):
                break
        logfile = open(ansible_log, 'r')
        self.addCleanup(logfile.close)

        def wait_for_stream(name):
            for x in iterate_timeout(30, "incoming streaming data"):
                if len(self.streaming_data.get(name, '')) > 0:
                    break

        # Start the finger gateway daemons
        gateway_unzoned, gateway_unzoned_address = self.runFingerGateway()
        gateway_us_west, gateway_us_west_address = self.runFingerGateway(
            zone='us-west')

        # This finger client runs against a finger gateway in a different zone
        # while there is no gateway in the worker zone yet. This should work.
        finger_client_us_west_alone = self._run_finger_client(
            build, gateway_us_west_address, name='us-west-alone')
        # The stream must go only via gateway_us_west
        wait_for_stream('us-west-alone')
        self.assertEqual(0, len(gateway_unzoned.history))
        self.assertEqual(1, len(gateway_us_west.history))
        gateway_unzoned.history.clear()
        gateway_us_west.history.clear()

        # This finger client runs against an unzoned finger gateway
        finger_client_unzoned = self._run_finger_client(
            build, gateway_unzoned_address, name='unzoned')
        wait_for_stream('unzoned')
        self.assertEqual(1, len(gateway_unzoned.history))
        self.assertEqual(0, len(gateway_us_west.history))
        gateway_unzoned.history.clear()
        gateway_us_west.history.clear()

        # Now start a finger gateway in the target zone.
        gateway_eu_central, gateway_eu_central_address = self.runFingerGateway(
            zone='eu-central')

        # This finger client runs against a finger gateway in a different zone
        # while there is a gateway in the worker zone. This should route via
        # the gateway in the worker zone.
        finger_client_us_west = self._run_finger_client(
            build, gateway_us_west_address, name='us-west')
        # The stream must go only via gateway_us_west
        wait_for_stream('us-west')
        self.assertEqual(0, len(gateway_unzoned.history))
        self.assertEqual(1, len(gateway_eu_central.history))
        self.assertEqual(1, len(gateway_us_west.history))
        gateway_unzoned.history.clear()
        gateway_eu_central.history.clear()
        gateway_us_west.history.clear()

        # This finger client runs against an unzoned finger gateway while there
        # is a target finger client. As it is unzoned it should not route via
        # The finger gateway in eu-central.
        finger_client_unzoned2 = self._run_finger_client(
            build, gateway_unzoned_address, name='unzoned2')
        wait_for_stream('unzoned2')
        self.assertEqual(1, len(gateway_unzoned.history))
        self.assertEqual(0, len(gateway_eu_central.history))
        self.assertEqual(0, len(gateway_us_west.history))
        gateway_unzoned.history.clear()
        gateway_eu_central.history.clear()
        gateway_us_west.history.clear()

        # This finger client runs against the target finger gateway.
        finger_client_eu_central = self._run_finger_client(
            build, gateway_eu_central_address, name='eu-central')
        wait_for_stream('eu-central')
        self.assertEqual(0, len(gateway_unzoned.history))
        self.assertEqual(1, len(gateway_eu_central.history))
        self.assertEqual(0, len(gateway_us_west.history))
        gateway_unzoned.history.clear()
        gateway_eu_central.history.clear()
        gateway_us_west.history.clear()

        # Allow the job to complete
        flag_file = os.path.join(build_dir, 'test_wait')
        open(flag_file, 'w').close()

        # Wait for the finger client to complete, which it should when
        # it's received the full log.
        finger_client_us_west_alone.join()
        finger_client_us_west.join()
        finger_client_eu_central.join()
        finger_client_unzoned.join()
        finger_client_unzoned2.join()

        self.waitUntilSettled()

        file_contents = logfile.read()
        logfile.close()
        self.log.debug("\n\nFile contents: %s\n\n", file_contents)
        self.log.debug("\n\nStreamed: %s\n\n",
                       self.streaming_data['us-west-alone'])
        self.assertEqual(file_contents, self.streaming_data['us-west-alone'])
        self.assertEqual(file_contents, self.streaming_data['us-west'])
        self.assertEqual(file_contents, self.streaming_data['unzoned'])
        self.assertEqual(file_contents, self.streaming_data['unzoned2'])
        self.assertEqual(file_contents, self.streaming_data['eu-central'])
