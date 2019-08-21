#!/usr/bin/env python
# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013-2014 OpenStack Foundation
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
import sys
import signal
import threading
import time

import zuul.cmd
import zuul.executor.server

from zuul.lib.config import get_default


class LogStreamerManager(object):
    def __init__(self, finger_port, job_dir):
        self._log_streamer_pid = None
        self.log = logging.getLogger("zuul.Executor.LogStreamerManager")
        self.finger_port = finger_port
        self.job_dir = job_dir
        self.executor = executor
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(
            target=self._run, name='log-streamer-manager', daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        self._start_log_streamer()
        while not self.stop_event.is_set():
            if not self.stop_event.wait(5):
                # Check that we havne't stopped yet
                pid, rc = os.waitpid(self._log_streamer_pid, os.WNOHANG)
                if pid == self._log_streamer_pid:
                    # Exit and force system level service management to
                    # restart the service.
                    self.log.error("Log streaming proxy died. "
                                   "Stopping Executor.")
                    self.executor.stop()

    def _start_log_streamer(self):
        pipe_read, pipe_write = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(pipe_write)
            import zuul.lib.log_streamer

            self.log.info("Starting log streamer")
            streamer = zuul.lib.log_streamer.LogStreamer(
                '::', self.finger_port, self.job_dir
            )

            # Keep running until the parent dies:
            pipe_read = os.fdopen(pipe_read)
            pipe_read.read()
            self.log.info("Stopping log streamer")
            streamer.stop()
            os._exit(0)
        else:
            os.close(pipe_read)
            self._log_streamer_pid = child_pid


class Executor(zuul.cmd.ZuulDaemonApp):
    app_name = 'executor'
    app_description = 'A standalone Zuul executor.'

    def createParser(self):
        parser = super(Executor, self).createParser()
        parser.add_argument('--keep-jobdir', dest='keep_jobdir',
                            action='store_true',
                            help='keep local jobdirs after run completes')
        parser.add_argument('command',
                            choices=zuul.executor.server.COMMANDS,
                            nargs='?')
        return parser

    def parseArguments(self, args=None):
        super(Executor, self).parseArguments()
        if self.args.command:
            self.args.nodaemon = True

    def exit_handler(self, signum, frame):
        self.executor.stop()
        self.executor.join()
        sys.exit(0)

    def run(self):
        if self.args.command in zuul.executor.server.COMMANDS:
            self.send_command(self.args.command)
            sys.exit(0)

        self.configure_connections(source_only=True)

        if self.config.has_option('executor', 'job_dir'):
            self.job_dir = os.path.expanduser(
                self.config.get('executor', 'job_dir'))
            if not os.path.isdir(self.job_dir):
                print("Invalid job_dir: {job_dir}".format(
                    job_dir=self.job_dir))
                sys.exit(1)
        else:
            self.job_dir = '/var/lib/zuul/builds'
            if not os.path.exists(self.job_dir):
                os.mkdir(self.job_dir)

        self.setup_logging('executor', 'log_config')
        self.log = logging.getLogger("zuul.Executor")

        self.finger_port = int(
            get_default(self.config, 'executor', 'finger_port',
                        zuul.executor.server.DEFAULT_FINGER_PORT)
        )

        ExecutorServer = zuul.executor.server.ExecutorServer
        self.executor = ExecutorServer(self.config, self.connections,
                                       jobdir_root=self.job_dir,
                                       keep_jobdir=self.args.keep_jobdir,
                                       log_streaming_port=self.finger_port)

        # These two classes reference each other so that the streamer manager
        # can stop the executor and the executor can stop the log streamer
        # manager depending on which event triggers the shutdown.
        self.log_streamer_manager = LogStreamerManager(
            self.finger_port, self.job_dir, self.executor
        )
        self.executor.log_streamer_manager = self.log_streamer_manager
        self.log_streamer_manager.start()

        self.executor.start()

        if self.args.nodaemon:
            signal.signal(signal.SIGTERM, self.exit_handler)
            while True:
                try:
                    signal.pause()
                except KeyboardInterrupt:
                    print("Ctrl + C: asking executor to exit nicely...\n")
                    self.exit_handler(signal.SIGINT, None)
        else:
            self.executor.join()


def main():
    Executor().main()


if __name__ == "__main__":
    main()
