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
import logging
import os.path
import tempfile

try:
    import SocketServer as ss  # python 2.x
except ImportError:
    import socketserver as ss  # python 3

import zuul.cmd


FINGER_PORT = 79


class RequestHandler(ss.BaseRequestHandler):
    def handle(self):
        job_id = self.request.recv(1024)
        job_id = job_id.rstrip()

        # validate job ID
        job_dir = os.path.join(self.server.jobdir_root, job_id)
        if not os.path.exists(job_dir):
            self.request.sendall('Job ID %s not found' % job_id)
            return

        # check if log file exists
        log_file = os.path.join(job_dir, 'ansible', 'ansible_log.txt')
        if not os.path.exists(log_file):
            self.request.sendall('Log not found for job %s' % job_id)
            return

        self.request.sendall('Streaming %s for job %s' % (log_file, job_id))


class FingerLogStreamer(zuul.cmd.ZuulApp):
    def __init__(self):
        super(FingerLogStreamer, self).__init__()
        self.jobdir_root = tempfile.gettempdir()

    def parse_arguments(self):
        parser = argparse.ArgumentParser(
            description='Zuul Finger Log Streamer')
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')
        self.args = parser.parse_args()

    def main(self):
        self.setup_logging('fingerd', 'log_config')
        self.log = logging.getLogger('zuul.cmd.fingerd.FingerLogStreamer')

        host = '0.0.0.0'
        self.log.debug("Starting fingerd service on %s:%s", host, FINGER_PORT)
        server = ss.ForkingTCPServer((host, FINGER_PORT), RequestHandler)
        server.jobdir_root = self.jobdir_root

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down")

        server.shutdown()
        server.server_close()


def main():
    server = FingerLogStreamer()
    server.parse_arguments()
    server.read_config()

    if server.config.has_option('zuul', 'jobdir_root'):
        server.jobdir_root = os.path.expanduser(
            server.config.get('zuul', 'jobdir_root'))

    server.main()

if __name__ == "__main__":
    main()
