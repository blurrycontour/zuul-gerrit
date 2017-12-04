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

import logging
import os
import signal
import socketserver
import threading

import zuul.cmd

from zuul.lib.config import get_default
from zuul.lib import streamer_utils


class RequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        port_loc = streamer_utils.get_port_location(job_uuid) # noqa
        pass


class FingerGateway(zuul.cmd.ZuulDaemonApp):
    '''
    Class for the daemon that will multiplex any finger requests to the
    appropriate Zuul executor handling the specified build.
    '''
    app_name = 'fingergw'
    app_description = 'The Zuul finger gateway.'

    def __init__(self):
        super(FingerGateway, self).__init__()
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
        self.log = logging.getLogger('zuul.FingerGateway')

        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        # Get values from configuration file
        host = get_default(self.config, 'fingergw', 'host', '::')
        port = int(get_default(self.config, 'fingergw', 'port', 79))
        user = get_default(self.config, 'fingergw', 'user', 'zuul')

        self.server = streamer_utils.CustomThreadingTCPServer(
            (host, port), RequestHandler, user=user)

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
        self.log.info('Stopped Zuul finger gateway')


def main():
    FingerGateway().main()


if __name__ == "__main__":
    main()
