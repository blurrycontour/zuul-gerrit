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

import functools
import logging
import socket
import threading

import zuul.rpcclient

from zuul.lib import streamer_utils


class RequestHandler(streamer_utils.BaseFingerRequestHandler):

    log = logging.getLogger("zuul.fingergw")

    def __init__(self, *args, **kwargs):
        self.rpc = kwargs.pop('rpc')
        super(RequestHandler, self).__init__(*args, **kwargs)

    def _fingerClient(self, server, port, build_uuid):
        '''
        Open a finger connection and return all streaming results.

        :param server: The remote server.
        :param port: The remote port.
        :param build_uuid: The build UUID to stream.

        Both IPv4 and IPv6 are supported.
        '''
        with socket.create_connection((server, port), timeout=10) as s:
            msg = "%s\n" % build_uuid    # Must have a trailing newline!
            s.sendall(msg.encode('utf-8'))
            while True:
                data = s.recv(1024)
                if data:
                    self.request.sendall(data)
                else:
                    break

    def handle(self):
        try:
            build_uuid = self.getCommand()

            # ----- Test -----
            # msg = 'Hello. Getting %s' % build_uuid
            # self.request.sendall(msg.encode('utf-8'))
            # return
            # ----- Test -----

            port_location = self.rpc.get_job_log_stream_address(build_uuid)
            self._fingerClient(
                self.request,
                port_location['server'],
                port_location['port'],
                build_uuid,
            )
        except Exception:
            self.log.exception('Finger request handling exception:')
            msg = 'Internal streaming error'
            self.request.sendall(msg.encode('utf-8'))
            return


class FingerGateway(object):

    log = logging.getLogger("zuul.fingergw")

    def __init__(self, gearman, address, user):
        '''
        Initialize the finger gateway.

        :param tuple gearman: Gearman connection information. This should
            include the server, port, SSL key, SSL cert, and SSL CA.
        :param tuple address: The address and port to bind to for our gateway.
        :param str user: The user to which we should drop privileges after
            binding to our address.
        '''
        self.gear_server = gearman[0]
        self.gear_port = gearman[1]
        self.gear_ssl_key = gearman[2]
        self.gear_ssl_cert = gearman[3]
        self.gear_ssl_ca = gearman[4]
        self.address = address
        self.user = user
        self.rpc = None
        self.server = None
        self.server_thread = None

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
            functools.partial(RequestHandler, rpc=self.rpc),
            user=self.user)

        # The socketserver shutdown() call will hang unless the call
        # to server_forever() happens in another thread. So let's do that.
        self.server_thread = threading.Thread(target=self._run)
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.rpc:
            self.rpc.shutdown()
