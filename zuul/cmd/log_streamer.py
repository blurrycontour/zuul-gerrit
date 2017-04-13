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
import daemon
import extras
import glob
import logging
import os
import os.path
import pwd
import re
import select
import signal
import tempfile
import time

try:
    import SocketServer as ss  # python 2.x
except ImportError:
    import socketserver as ss  # python 3

import zuul.cmd

# as of python-daemon 1.6 it doesn't bundle pidlockfile anymore
# instead it depends on lockfile-0.9.1 which uses pidfile.
pid_file_module = extras.try_imports(['daemon.pidlockfile', 'daemon.pidfile'])


FINGER_PORT = 79
USER = 'zuul'


class Log(object):

    def __init__(self, path):
        self.path = path
        self.file = open(path)
        self.stat = os.stat(path)
        self.size = self.stat.st_size


class RequestHandler(ss.BaseRequestHandler):
    '''
    Class to handle a single log streaming request.

    The log streaming code was blatantly stolen from zuul_console.py. Only
    the (class/method/attribute) names were changed to protect the innocent.
    '''

    def handle(self):
        self.log = logging.getLogger('zuul.cmd.log_streamer.RequestHandler')

        try:
            self.change_privs()
        except Exception:
            self.log.exception('Cannot change privileges:')
            self.request.sendall('Server-side error')
            return

        build_uuid = self.request.recv(1024)
        build_uuid = build_uuid.rstrip()

        # validate build ID
        if not re.match("[0-9A-Fa-f]+$", build_uuid):
            self.request.sendall('Build ID %s is not valid' % build_uuid)
            return

        # temp dir is "<buildUUID>_<random>" format
        job_dir_prefix = os.path.join(self.server.jobdir_root, build_uuid)
        matches = glob.glob("%s_*" % job_dir_prefix)
        if len(matches) != 1:
            self.request.sendall('Build ID %s not found' % build_uuid)
            return
        job_dir = matches[0]

        # check if log file exists
        log_file = os.path.join(job_dir, 'ansible', 'ansible_log.txt')
        if not os.path.exists(log_file):
            self.request.sendall('Log not found for build ID %s' % build_uuid)
            return

        self.log.info('Streaming %s to %s', log_file, self.client_address)
        self.stream_log(log_file)
        self.log.info('Done streaming to %s', self.client_address)

    def change_privs(self):
        '''
        Drop our privileges to the zuul user.
        '''
        if os.getuid() != 0:
            return
        pw = pwd.getpwnam(USER)
        os.setgroups([])
        os.setgid(pw.pw_gid)
        os.setuid(pw.pw_uid)

    def stream_log(self, log_file):
        log = None
        while True:
            if log is not None:
                try:
                    log.file.close()
                except:
                    pass
            while True:
                try:
                    log = self.chunk_log(log_file)
                except Exception:
                    self.log.exception('Cannot access log %s:', log_file)
                    return

                if log:
                    break
                time.sleep(0.5)
            while True:
                if self.follow_log(log):
                    break
                else:
                    return

    def chunk_log(self, log_file):
        log = Log(log_file)
        while True:
            chunk = log.file.read(4096)
            if not chunk:
                break
            self.request.send(chunk)
        return log

    def follow_log(self, log):
        while True:
            # As long as we have unread data, keep reading/sending
            while True:
                chunk = log.file.read(4096)
                if chunk:
                    self.request.send(chunk)
                else:
                    break

            # At this point, we are waiting for more data to be written
            time.sleep(0.5)

            # Check to see if the remote end has sent any data, if so,
            # discard
            r, w, e = select.select([self.request], [], [self.request], 0)
            if self.request in e:
                return False
            if self.request in r:
                ret = self.request.recv(1024)
                # Discard anything read, if input is eof, it has
                # disconnected.
                if not ret:
                    return False

            # See if the file has been truncated
            try:
                st = os.stat(log.path)
                if (st.st_ino != log.stat.st_ino or
                    st.st_size < log.size):
                    return True
            except Exception:
                return True
            log.size = st.st_size


class LogStreamer(zuul.cmd.ZuulApp):

    def __init__(self):
        super(LogStreamer, self).__init__()
        self.jobdir_root = tempfile.gettempdir()

    def parse_arguments(self):
        parser = argparse.ArgumentParser(
            description='Zuul Log Streamer')
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('-d', dest='nodaemon', action='store_true',
                            help='do not run as a daemon')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')
        self.args = parser.parse_args()

    def exit_handler(self, signum, frame):
        self.log.info('Shutting down log streamer')
        self.server.shutdown()
        self.server.server_close()

    def main(self):
        self.setup_logging('log_streamer', 'log_config')
        self.log = logging.getLogger('zuul.cmd.log_streamer.LogStreamer')

        signal.signal(signal.SIGUSR1, self.exit_handler)

        host = '0.0.0.0'
        self.log.info('Starting log streamer')
        self.server = ss.ForkingTCPServer((host, FINGER_PORT), RequestHandler)
        self.server.jobdir_root = self.jobdir_root

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            self.exit_handler(signal.SIGINT, None)


def main():
    server = LogStreamer()
    server.parse_arguments()
    server.read_config()

    if server.config.has_option('zuul', 'jobdir_root'):
        server.jobdir_root = os.path.expanduser(
            server.config.get('zuul', 'jobdir_root'))

    if server.config.has_option('log_streamer', 'pidfile'):
        pid_fn = os.path.expanduser(server.config.get('log_streamer', 'pidfile'))
    else:
        pid_fn = '/var/run/zuul-log-streamer/zuul-log-streamer.pid'
    pid = pid_file_module.TimeoutPIDLockFile(pid_fn, 10)

    if server.args.nodaemon:
        server.main()
    else:
        with daemon.DaemonContext(pidfile=pid):
            server.main()


if __name__ == "__main__":
    main()
