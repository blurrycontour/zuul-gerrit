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

import functools
import json
import logging
import socket
import ssl
import threading
import time

import gear

import zuul.rpcclient

from zuul.lib import commandsocket
from zuul.lib import streamer_utils
from zuul.lib.config import get_default
from zuul.lib.gear_utils import getGearmanFunctions
from zuul.lib.gearworker import ZuulGearWorker
from zuul.rpcclient import RPCFailure

COMMANDS = ['stop']


class RequestHandler(streamer_utils.BaseFingerRequestHandler):
    '''
    Class implementing the logic for handling a single finger request.
    '''

    log = logging.getLogger("zuul.fingergw")

    def __init__(self, *args, **kwargs):
        self.fingergw = kwargs.pop('fingergw')
        super(RequestHandler, self).__init__(*args, **kwargs)

    def _fingerClient(self, server, port, build_uuid, use_ssl):
        '''
        Open a finger connection and return all streaming results.

        :param server: The remote server.
        :param port: The remote port.
        :param build_uuid: The build UUID to stream.

        Both IPv4 and IPv6 are supported.
        '''
        with socket.create_connection((server, port), timeout=10) as s:
            if use_ssl:
                context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = False
                context.load_cert_chain(self.fingergw.finger_client_ssl_cert,
                                        self.fingergw.finger_client_ssl_key)
                context.load_verify_locations(
                    self.fingergw.finger_client_ssl_ca)
                s = context.wrap_socket(s, server_hostname=server)

            # timeout only on the connection, let recv() wait forever
            s.settimeout(None)
            msg = "%s\n" % build_uuid    # Must have a trailing newline!
            s.sendall(msg.encode('utf-8'))
            while True:
                data = s.recv(1024)
                if data:
                    self.request.sendall(data)
                else:
                    break

    def handle(self):
        '''
        This method is called by the socketserver framework to handle an
        incoming request.
        '''
        server = None
        port = None
        try:
            build_uuid = self.getCommand()
            port_location = self.fingergw.rpc.get_job_log_stream_address(
                build_uuid, source_zone=self.fingergw.zone)

            if not port_location:
                msg = 'Invalid build UUID %s' % build_uuid
                self.request.sendall(msg.encode('utf-8'))
                return

            server = port_location['server']
            port = port_location['port']
            use_ssl = port_location.get('use_ssl', False)
            self._fingerClient(server, port, build_uuid, use_ssl)
        except BrokenPipeError:   # Client disconnect
            return
        except Exception:
            self.log.exception(
                'Finger request handling exception (%s:%s):',
                server, port)
            msg = 'Internal streaming error'
            self.request.sendall(msg.encode('utf-8'))
            return


class FingerGateway(object):
    '''
    Class implementing the finger multiplexing/gateway logic.

    For each incoming finger request, a new thread is started that will
    be responsible for finding which Zuul executor is executing the
    requested build (by asking Gearman), forwarding the request to that
    executor, and streaming the results back to our client.
    '''

    log = logging.getLogger("zuul.fingergw")
    handler_class = RequestHandler

    def __init__(self, config, command_socket, pid_file):
        '''
        Initialize the finger gateway.

        :param tuple gearman: Gearman connection information. This should
            include the server, port, SSL key, SSL cert, and SSL CA.
        :param tuple address: The address and port to bind to for our gateway.
        :param str user: The user to which we should drop privileges after
            binding to our address.
        :param str command_socket: Path to the daemon command socket.
        :param str pid_file: Path to the daemon PID file.
        '''

        gear_server = get_default(config, 'gearman', 'server')
        gear_port = get_default(config, 'gearman', 'port', 4730)
        gear_ssl_key = get_default(config, 'gearman', 'ssl_key')
        gear_ssl_cert = get_default(config, 'gearman', 'ssl_cert')
        gear_ssl_ca = get_default(config, 'gearman', 'ssl_ca')

        self.gear_server = gear_server
        self.gear_port = gear_port
        self.gear_ssl_key = gear_ssl_key
        self.gear_ssl_cert = gear_ssl_cert
        self.gear_ssl_ca = gear_ssl_ca

        host = get_default(config, 'fingergw', 'listen_address', '::')
        self.port = int(get_default(config, 'fingergw', 'port', 79))
        self.public_port = int(get_default(
            config, 'fingergw', 'public_port', self.port))
        user = get_default(config, 'fingergw', 'user', None)

        self.address = (host, self.port)
        self.user = user
        self.pid_file = pid_file

        self.rpc = None
        self.server = None
        self.server_thread = None

        self.command_thread = None
        self.command_running = False

        self.command_socket = command_socket

        # Fingergw server ssl settings
        self.finger_server_ssl_key = get_default(
            config, 'fingergw', 'server_ssl_key')
        self.finger_server_ssl_cert = get_default(
            config, 'fingergw', 'server_ssl_cert')
        self.finger_server_ssl_ca = get_default(
            config, 'fingergw', 'server_ssl_ca')

        # Fingergw client ssl settings
        self.finger_client_ssl_key = get_default(
            config, 'fingergw', 'client_ssl_key')
        self.finger_client_ssl_cert = get_default(
            config, 'fingergw', 'client_ssl_cert')
        self.finger_client_ssl_ca = get_default(
            config, 'fingergw', 'client_ssl_ca')

        self.command_map = dict(
            stop=self.stop,
        )

        self.hostname = get_default(config, 'fingergw', 'hostname',
                                    socket.getfqdn())
        self.zone = get_default(config, 'fingergw', 'zone')

        if self.zone is not None:
            jobs = {
                'fingergw:info:%s' % self.zone: self.handle_info,
            }
            self.gearworker = ZuulGearWorker(
                'Finger Gateway',
                'zuul.fingergw',
                'fingergw-gearman-worker',
                config,
                jobs)
        else:
            self.gearworker = None

    def handle_info(self, job):
        self.log.debug('Got %s job: %s', job.name, job.unique)
        info = {
            'server': self.hostname,
            'port': self.public_port,
        }
        if self.zone:
            info['zone'] = self.zone
        if all([self.finger_server_ssl_key,
                self.finger_server_ssl_cert, self.finger_server_ssl_ca]):
            info['use_ssl'] = True
        job.sendWorkComplete(json.dumps(info))

    def _runCommand(self):
        while self.command_running:
            try:
                command = self.command_socket.get().decode('utf8')
                if command != '_stop':
                    self.command_map[command]()
                else:
                    return
            except Exception:
                self.log.exception("Exception while processing command")

    def _run(self):
        try:
            self.server.serve_forever()
        except Exception:
            self.log.exception('Abnormal termination:')
            raise

    def start(self):
        self.rpc = zuul.rpcclient.RPCClient(
            self.gear_server,
            self.gear_port,
            self.gear_ssl_key,
            self.gear_ssl_cert,
            self.gear_ssl_ca)

        self.server = streamer_utils.CustomThreadingTCPServer(
            self.address,
            functools.partial(self.handler_class, fingergw=self),
            user=self.user,
            pid_file=self.pid_file)

        # Update port that we really use if we configured a port of 0
        if self.public_port == 0:
            self.public_port = self.server.socket.getsockname()[1]

        # Start the command processor after the server and privilege drop
        if self.command_socket:
            self.log.debug("Starting command processor")
            self.command_socket = commandsocket.CommandSocket(
                self.command_socket)
            self.command_socket.start()
            self.command_running = True
            self.command_thread = threading.Thread(
                target=self._runCommand, name='command')
            self.command_thread.daemon = True
            self.command_thread.start()

        # The socketserver shutdown() call will hang unless the call
        # to server_forever() happens in another thread. So let's do that.
        self.server_thread = threading.Thread(target=self._run)
        self.server_thread.daemon = True
        self.server_thread.start()

        # Register this finger gateway in case we are zoned
        if self.gearworker:
            self.log.info('Starting gearworker')
            self.gearworker.start()

        self.log.info("Finger gateway is started")

    def stop(self):
        if self.gearworker:
            self.gearworker.stop()

        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
                self.server = None
            except Exception:
                self.log.exception("Error stopping TCP server:")

        if self.rpc:
            try:
                self.rpc.shutdown()
                self.rpc = None
            except Exception:
                self.log.exception("Error stopping RCP client:")

        if self.command_socket:
            self.command_running = False

            try:
                self.command_socket.stop()
            except Exception:
                self.log.exception("Error stopping command socket:")

        self.log.info("Finger gateway is stopped")

    def wait(self):
        '''
        Wait on the gateway to shutdown.
        '''
        self.gearworker.join()
        self.server_thread.join()


class FingerClient:
    log = logging.getLogger("zuul.FingerClient")

    def __init__(self, server, port, ssl_key=None, ssl_cert=None, ssl_ca=None):
        self.log.debug("Connecting to gearman at %s:%s" % (server, port))
        self.gearman = gear.Client()
        self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca,
                               keepalive=True, tcp_keepidle=60,
                               tcp_keepintvl=30, tcp_keepcnt=5)
        self.log.debug("Waiting for gearman")
        self.gearman.waitForServer()

    def submitJob(self, name, data):
        self.log.debug("Submitting job %s with data %s" % (name, data))
        job = gear.TextJob(name,
                           json.dumps(data),
                           unique=str(time.time()))
        self.gearman.submitJob(job, timeout=300)

        self.log.debug("Waiting for job completion")
        while not job.complete:
            time.sleep(0.1)
        if job.exception:
            raise RPCFailure(job.exception)
        self.log.debug("Job complete, success: %s" % (not job.failure))
        return job

    def shutdown(self):
        self.gearman.shutdown()

    def get_fingergw_in_zone(self, zone):
        job_name = 'fingergw:info:%s' % zone
        functions = getGearmanFunctions(self.gearman)
        if job_name not in functions:
            # There is no matching fingergw
            return None

        job = self.submitJob(job_name, {})
        if job.failure:
            return None
        else:
            return json.loads(job.data[0])
