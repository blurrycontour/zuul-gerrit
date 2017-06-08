#!/usr/bin/env python

# Copyright (c) 2016 IBM Corp.
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

NODE_LOG_STREAM_PATH = '/tmp'
NODE_LOG_STREAM_FILE = 'console-{uuid}.log'
NODE_LOG_STREAM_PORT = 19885


class Log(object):

    def __init__(self, path):
        self.path = path
        self.file = open(path)
        self.stat = os.stat(path)
        self.size = self.stat.st_size


class BaseRequestHandler(ss.BaseRequestHandler):
    '''
    Class to handle a single log streaming request.

    The log streaming code was blatantly stolen from zuul_console.py. Only
    the (class/method/attribute) names were changed to protect the innocent.
    '''

    MAX_REQUEST_LEN = 1024
    REQUEST_TIMEOUT = 10

    def get_command(self):
        poll = select.poll()
        bitmask = (select.POLLIN | select.POLLERR |
                   select.POLLHUP | select.POLLNVAL)
        poll.register(self.request, bitmask)
        buffer = b''
        ret = None
        start = time.time()
        while True:
            elapsed = time.time() - start
            timeout = max(self.REQUEST_TIMEOUT - elapsed, 0)
            if not timeout:
                raise Exception("Timeout while waiting for input")
            for fd, event in poll.poll(timeout):
                if event & select.POLLIN:
                    buffer += self.request.recv(self.MAX_REQUEST_LEN)
                else:
                    raise Exception("Received error event")
            if len(buffer) >= self.MAX_REQUEST_LEN:
                raise Exception("Request too long")
            try:
                ret = buffer.decode('utf-8')
                x = ret.find('\n')
                if x > 0:
                    return ret[:x]
            except UnicodeDecodeError:
                pass

    def validate_uuid(self, requested_uuid):
        return re.match("[0-9A-Fa-f]+$", requested_uuid)

    def handle(self):
        requested_uuid = self.get_command()
        requested_uuid = requested_uuid.rstrip()

        log_file = self.make_log_file(requested_uuid)
        if not log_file:
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
            self.request.send(chunk.encode('utf-8'))
        return log

    def follow_log(self, log):
        while True:
            # As long as we have unread data, keep reading/sending
            while True:
                chunk = log.file.read(4096)
                if chunk:
                    self.request.send(chunk.encode('utf-8'))
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


class FingerRequestHandler(BaseRequestHandler):

    def make_log_file(self, requested_uuid):
        # validate ID
        if not self.validate_uuid(requested_uuid):
            msg = 'Build ID %s is not valid' % requested_uuid
            self.request.sendall(msg.encode("utf-8"))
            return

        job_dir = os.path.join(self.server.jobdir_root, requested_uuid)
        if not os.path.exists(job_dir):
            msg = 'Build ID %s not found' % requested_uuid
            self.request.sendall(msg.encode("utf-8"))
            return

        # check if log file exists
        log_file = os.path.join(job_dir, 'ansible', 'job-output.txt')
        if not os.path.exists(log_file):
            msg = 'Log not found for Build ID %s' % requested_uuid
            self.request.sendall(msg.encode("utf-8"))
            return

        return log_file


class NodeRequestHandler(BaseRequestHandler):

    def make_log_file(self, requested_uuid):

        # validate ID
        if not self.validate_uuid(requested_uuid):
            msg = 'Log ID %s is not valid' % requested_uuid
            self.request.sendall(msg.encode("utf-8"))
            return

        log_file = self.server.file_template.format(uuid=requested_uuid)

        return log_file


class V6ForkingTCPServer(ss.ForkingTCPServer):
    address_family = socket.AF_INET6


class CustomForkingTCPServer(V6ForkingTCPServer):
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
        try:
            self.socket.shutdown(socket.SHUT_RD)
            self.socket.close()
        except socket.error as e:
            # If it's already closed, don't error.
            if e.errno == socket.EBADF:
                return
            raise


class LogStreamer(object):
    '''
    Class implementing log streaming over the finger daemon port.
    '''

    def __init__(self, user, host, port, jobdir_root):
        self.server = CustomForkingTCPServer((host, port),
                                             FingerRequestHandler,
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


def get_node_log_streamer(
        host='::', port=NODE_LOG_STREAM_PORT, path=NODE_LOG_STREAM_PATH):
    '''Factory function for making an on-node log streamer.'''
    server = V6ForkingTCPServer((host, port), NodeRequestHandler)
    server.file_template = os.path.join(path, NODE_LOG_STREAM_FILE)
    return server
