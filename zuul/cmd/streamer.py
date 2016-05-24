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
import extras
import lockfile.pidlockfile
import logging
import os
import signal
import sys
import threading

import zuul.cmd
import zuul.streamer

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])


class WebStreamer(zuul.cmd.ZuulApp):

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
        self.streamer.stop()

    def _main(self):
        params = dict()

        if self.config.has_option('streamer', 'gearman_server'):
            params['gear_server'] = self.config.get('streamer',
                                                    'gearman_server')

        if self.config.has_option('streamer', 'gearman_port'):
            params['gear_port'] = self.config.get('streamer', 'gearman_port')

        if self.config.has_option('streamer', 'listen_address'):
            params['listen_address'] = self.config.get('streamer',
                                                       'listen_address')
        if self.config.has_option('streamer', 'port'):
            params['listen_port'] = self.config.get('streamer', 'port')

        try:
            self.streamer = zuul.streamer.ZuulStreamer(**params)
        except Exception as e:
            self.log.exception("Error creating ZuulStreamer:")
            sys.exit(1)

        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('Zuul Web Streamer starting')

        # The main thread event loop has to be passed in to the streamer
        # because we start it in a separate thread, where it cannot access
        # it, otherwise,
        loop = asyncio.get_event_loop()
        self.thread = threading.Thread(target=self.streamer.run,
                                       args=(loop,),
                                       name='streamer')
        self.thread.start()

        try:
            signal.pause()
        except KeyboardInterrupt:
            print("Ctrl + C: asking streamer to exit nicely...\n")
            self.exit_handler(signal.SIGINT, None)

        self.thread.join()
        self.log.info("Zuul Web Streamer stopped")

    def main(self):
        self.setup_logging('streamer', 'log_config')
        self.log = logging.getLogger("zuul.WebStreamer")

        try:
            self._main()
        except Exception:
            self.log.exception("Exception from WebStreamer:")


def main():
    server = WebStreamer()
    server.parse_arguments()
    server.read_config()

    if server.config.has_option('streamer', 'pidfile'):
        pid_fn = os.path.expanduser(server.config.get('streamer', 'pidfile'))
    else:
        pid_fn = '/var/run/zuul-web-streamer/zuul-web-streamer.pid'

    if server.args.nodaemon:
        server.main()
    else:
        # NOTE(Shrews): The python-daemon library, normally used for the
        # Zuul daemons, doesn't seem to play nicely with either the autobahn
        # library or asyncio itself.
        child_pid = os.fork()
        if child_pid == 0:
            pidfile = lockfile.pidlockfile.PIDLockFile(pid_fn)
            pidfile.acquire()
            server.main()
            pidfile.release()
