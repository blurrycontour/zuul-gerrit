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

import os
import os.path
import pwd
import re
import select
import socket
import threading
import time

try:
    import SocketServer as ss  # python 2.x
except ImportError:
    import socketserver as ss  # python 3


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

        self.stream_log(log_file)

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
        self.jobdir_root = kwargs.pop('jobdir_root')
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
        self.allow_reuse_address = True
        ss.ForkingTCPServer.server_bind(self)
        if self.user:
            self.change_privs()

    def server_close(self):
        '''
        Overridden from base class to shutdown the socket immediately.
        '''
        self.socket.shutdown(socket.SHUT_RD)
        self.socket.close()


class LogStreamer(object):
    '''
    Class implementing log streaming over the finger daemon port.
    '''

    def __init__(self, user, host, port, jobdir_root):
        self.server = CustomForkingTCPServer((host, port),
                                             RequestHandler,
                                             user=user,
                                             jobdir_root=jobdir_root)

        # We start the actual serving within a thread so we can return to
        # the owner.
        self.thd = threading.Thread(target=self.server.serve_forever)
        self.thd.daemon = True
        self.thd.start()

    def stop(self):
        if self.thd.isAlive():
            self.server.shutdown()
            self.server.server_close()
