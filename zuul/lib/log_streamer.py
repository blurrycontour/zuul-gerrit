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

import extras
import logging
import os
import os.path
import pwd
import re
import select
import signal
import tempfile
import threading
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

        build_uuid = self.request.recv(1024)
        build_uuid = build_uuid.rstrip()

        # validate build ID
        if not re.match("[0-9A-Fa-f]+$", build_uuid):
            self.request.sendall('Build ID %s is not valid' % build_uuid)
            return

        job_dir = os.path.join(self.server.jobdir_root, build_uuid)
        if not os.path.exists(job_dir):
            self.request.sendall('Build ID %s not found' % build_uuid)
            return

        # check if log file exists
        log_file = os.path.join(job_dir, 'ansible', 'ansible_log.txt')
        if not os.path.exists(log_file):
            self.request.sendall('Log not found for build ID %s' % build_uuid)
            return

        self.log.info('Streaming %s to %s', log_file, self.client_address)
        self.stream_log(log_file)
        self.log.info('Done streaming to %s', self.client_address)

    def stream_log(self, log_file):
        log = None
        while True:
            if log is not None:
                try:
                    log.file.close()
                except:
                    pass
            while True:
                log = self.chunk_log(log_file)
                if log:
                    break
                time.sleep(0.5)
            while True:
                if self.follow_log(log):
                    break
                else:
                    return

    def chunk_log(self, log_file):
        try:
            log = Log(log_file)
        except Exception:
            return
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


class CustomForkingTCPServer(ss.ForkingTCPServer):
    '''
    Custom version that allows us to drop privileges after port binding.
    '''
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        # For some reason, setting custom attributes does not work if we
        # call the base class __init__ first. Wha??
        ss.ForkingTCPServer.__init__(self, *args, **kwargs)

    def change_privs(self):
        '''
        Drop our privileges to the zuul user.
        '''
        if os.getuid() != 0:
            return
        pw = pwd.getpwnam(self.user)
        os.setgroups([])
        os.setgid(pw.pw_gid)
        os.setuid(pw.pw_uid)
        os.umask(0o022)

    def server_bind(self):
        ss.ForkingTCPServer.server_bind(self)
        self.change_privs()


class LogStreamer(zuul.cmd.ZuulApp):
    '''
    Class implementing log streaming over the finger daemon port.

    We derive from the ZuulApp base class to get access to logging
    methods.
    '''

    def __init__(self, user, config):
        '''
        LogStreamer initializer.

        :param str user: User to drop to for request handling.
        :param config: The zuul config object.
        '''
        super(LogStreamer, self).__init__()

        self.config = config
        if self.config.has_option('zuul', 'jobroot_dir'):
            self.jobdir_root = self.config.get('zuul', 'jobdir_root')
        else:
            self.jobdir_root = tempfile.gettempdir()

        self.setup_logging('log_streamer', 'log_config')
        self.log = logging.getLogger('zuul.cmd.log_streamer.LogStreamer')

        signal.signal(signal.SIGUSR1, self.exit_handler)

        host = '0.0.0.0'
        self.log.info('Starting log streamer')
        self.server = CustomForkingTCPServer((host, FINGER_PORT),
                                             RequestHandler, user=user)
        self.server.jobdir_root = self.jobdir_root

        # We start the actual serving within a thread so we can return to
        # the owner.
        t = threading.Thread(target=self.server.serve_forever)
        t.daemon = True
        t.start()

    def exit_handler(self, signum, frame):
        self.log.info('Shutting down log streamer')
        self.server.shutdown()
        self.server.server_close()
