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

import argparse
import daemon
import extras

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])

import logging
import os
import socket
import sys
import signal

import zuul.cmd
import zuul.executor.server

# No zuul imports that pull in paramiko here; it must not be
# imported until after the daemonization.
# https://github.com/paramiko/paramiko/issues/59
# Similar situation with gear and statsd.


class Executor(zuul.cmd.ZuulApp):

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description='Zuul executor.')
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('-d', dest='nodaemon', action='store_true',
                            help='do not run as a daemon')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')
        parser.add_argument('--keep-jobdir', dest='keep_jobdir',
                            action='store_true',
                            help='keep local jobdirs after run completes')
        parser.add_argument('command',
                            choices=zuul.executor.server.COMMANDS,
                            nargs='?')

        self.args = parser.parse_args()

    def send_command(self, cmd):
        if self.config.has_option('zuul', 'state_dir'):
            state_dir = os.path.expanduser(
                self.config.get('zuul', 'state_dir'))
        else:
            state_dir = '/var/lib/zuul'
        path = os.path.join(state_dir, 'executor.socket')
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        s.sendall('%s\n' % cmd)

    def exit_handler(self):
        self.executor.stop()
        self.executor.join()

    def main(self, daemon=True):
        # See comment at top of file about zuul imports

        self.setup_logging('executor', 'log_config')

        self.log = logging.getLogger("zuul.Executor")

        jobdir_root = None
        if self.config.has_option('zuul', 'jobdir_root'):
            jobdir_root = os.path.expanduser(
                self.config.get('zuul', 'jobdir_root'))
            if not os.path.isdir(jobdir_root):
                print("Invalid jobdir_root: {jobdir_root}".format(
                    jobdir_root=jobdir_root))
                sys.exit(1)

        ExecutorServer = zuul.executor.server.ExecutorServer
        self.executor = ExecutorServer(self.config, self.connections,
                                       jobdir_root=jobdir_root,
                                       keep_jobdir=self.args.keep_jobdir)
        self.executor.start()

        signal.signal(signal.SIGUSR2, zuul.cmd.stack_dump_handler)
        if daemon:
            self.executor.join()
        else:
            while True:
                try:
                    signal.pause()
                except KeyboardInterrupt:
                    print("Ctrl + C: asking executor to exit nicely...\n")
                    self.exit_handler()
                    sys.exit(0)


def main():
    server = Executor()
    server.parse_arguments()
    server.read_config()

    if server.args.command in zuul.executor.server.COMMANDS:
        server.send_command(server.args.command)
        sys.exit(0)

    server.configure_connections(source_only=True)

    if server.config.has_option('executor', 'pidfile'):
        pid_fn = os.path.expanduser(server.config.get('executor', 'pidfile'))
    else:
        pid_fn = '/var/run/zuul-executor/zuul-executor.pid'
    pid = pid_file_module.TimeoutPIDLockFile(pid_fn, 10)

    if server.args.nodaemon:
        server.main(False)
    else:
        with daemon.DaemonContext(pidfile=pid):
            server.main(True)


if __name__ == "__main__":
    sys.path.insert(0, '.')
    main()
