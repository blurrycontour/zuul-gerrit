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
import os
import signal
import socket
import threading

import zuul.cmd
import zuul.rpcclient

from zuul.lib.config import get_default
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
        for res in socket.getaddrinfo(server, port,
                                      socket.AF_UNSPEC, socket.SOCK_STREAM):
            af, socktype, proto, cannonname, sa = res
            try:
                s = socket.socket(af, socktype, proto)
            except OSError:
                s = None
                continue

            try:
                s.connect(sa)
            except OSError:
                s.close()
                s = None
                continue
            break

        if s is None:
            raise Exception(
                'Could not open finger connection (%s,%s) for build UUID %s' %
                (server, port, build_uuid))

        # Pass through the streaming data
        with s:
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
        except Exception:
            self.log.exception('Failure during getCommand:')
            msg = 'Internal streaming error'
            self.request.sendall(msg.encode('utf-8'))
            return

        build_uuid = build_uuid.rstrip()

        try:
            port_location = self.rpc.get_job_log_stream_address(build_uuid)
        except Exception as e:
            self.log.exception('Unknown Gearman exception:')
            msg = 'Internal streaming error'
            self.request.sendall(msg.encode('utf-8'))
            return

        try:
            self._fingerClient(
                self.request,
                port_location['server'],
                port_location['port'],
                build_uuid,
            )
        except Exception as e:
            self.log.exception('Failure from finger client:')
            msg = 'Internal streaming error'
            self.request.sendall(msg.decode('utf-8'))
            return


class FingerGateway(zuul.cmd.ZuulDaemonApp):
    '''
    Class for the daemon that will distribute any finger requests to the
    appropriate Zuul executor handling the specified build UUID.
    '''
    app_name = 'fingergw'
    app_description = 'The Zuul finger gateway.'

    def __init__(self):
        super(FingerGateway, self).__init__()
        self.rpc = None
        self.server_thread = None

    def exit_handler(self, signum, frame):
        self.stop()
        os._exit(0)

    def _run(self):
        try:
            self.server.serve_forever()
        except Exception:
            self.log.exception('Abnormal termination:')
            raise

    def run(self):
        '''
        Main entry point for the FingerGateway.

        Called by the main() method of the parent class.
        '''
        self.setup_logging('fingergw', 'log_config')
        self.log = logging.getLogger('zuul.fingergw')

        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        # Get values from configuration file
        host = get_default(self.config, 'fingergw', 'host', '::')
        port = int(get_default(self.config, 'fingergw', 'port', 79))
        user = get_default(self.config, 'fingergw', 'user', 'zuul')
        gear_server = get_default(self.config, 'gearman', 'server')
        gear_port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')

        # Create a shared RPC client
        self.rpc = zuul.rpcclient.RPCClient(
            gear_server, gear_port, ssl_key, ssl_cert, ssl_ca)

        self.server = streamer_utils.CustomThreadingTCPServer(
            (host, port),
            functools.partial(RequestHandler, rpc=self.rpc),
            user=user)

        self.log.info('Starting Zuul finger gateway')

        # The socketserver shutdown() call will hang unless the call
        # to server_forever() happens in another thread. So let's do that.
        self.server_thread = threading.Thread(target=self._run)
        self.server_thread.daemon = True
        self.server_thread.start()

        while True:
            try:
                signal.pause()
            except KeyboardInterrupt:
                print("Ctrl + C: shutting down finger gateway...\n")
                self.exit_handler(signal.SIGINT, None)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        if self.rpc:
            self.rpc.shutdown()
        self.log.info('Stopped Zuul finger gateway')


def main():
    FingerGateway().main()


if __name__ == "__main__":
    main()
