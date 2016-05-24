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

import argparse
import asyncio
import daemon
import extras
import lockfile.pidlockfile
import logging
import os
import signal
import sys
import threading

import zuul.cmd
import zuul.web

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])


class WebServer(zuul.cmd.ZuulApp):

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description='Zuul Web Log Streamer.')
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('-d', dest='nodaemon', action='store_true',
                            help='do not run as a daemon')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')
        self.args = parser.parse_args()

    def exit_handler(self, signum, frame):
        self.web.stop()

    def _main(self):
        params = dict()

        if self.config.has_option('web', 'gearman_server'):
            params['gear_server'] = self.config.get('web', 'gearman_server')

        if self.config.has_option('web', 'gearman_port'):
            params['gear_port'] = self.config.get('web', 'gearman_port')

        if self.config.has_option('web', 'listen_address'):
            params['listen_address'] = self.config.get('web', 'listen_address')
        if self.config.has_option('web', 'port'):
            params['listen_port'] = self.config.get('web', 'port')

        try:
            self.web = zuul.web.ZuulWeb(**params)
        except Exception as e:
            self.log.exception("Error creating ZuulWeb:")
            sys.exit(1)

        loop = asyncio.get_event_loop()
        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('Zuul Web Server starting')
        self.thread = threading.Thread(target=self.web.run,
                                       args=(loop,),
                                       name='web')
        self.thread.start()

        try:
            signal.pause()
        except KeyboardInterrupt:
            print("Ctrl + C: asking web server to exit nicely...\n")
            self.exit_handler(signal.SIGINT, None)

        self.thread.join()
        loop.stop()
        loop.close()
        self.log.info("Zuul Web Server stopped")

    def main(self):
        self.setup_logging('web', 'log_config')
        self.log = logging.getLogger("zuul.WebServer")

        try:
            self._main()
        except Exception:
            self.log.exception("Exception from WebServer:")


def main():
    server = WebServer()
    server.parse_arguments()
    server.read_config()

    if server.config.has_option('web', 'pidfile'):
        pid_fn = os.path.expanduser(server.config.get('web', 'pidfile'))
    else:
        pid_fn = '/var/run/zuul-web/zuul-web.pid'
    pid = pid_file_module.TimeoutPIDLockFile(pid_fn, 10)

    if server.args.nodaemon:
        server.main()
    else:
        with daemon.DaemonContext(pidfile=pid):
            server.main()
