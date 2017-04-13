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

import socket
try:
    import SocketServer as ss  # 2.x
except ImportError:
    import socketserver as ss  # 3.0

FINGER_PORT = 79

class RequestHandler(ss.BaseRequestHandler):
    def handle(self):
        try:
            self._handle()
        except Exception as e:
            print("Exception handling request: %s" % e)

    def _handle(self):
        job_id = self.request.recv(1024)
        job_id = job_id.rstrip()
        self.request.sendall("Streaming console for job %s" % job_id)

def main():
    host = '0.0.0.0'
    server = ss.ForkingTCPServer((host, FINGER_PORT), RequestHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")

    server.shutdown()
    server.server_close()

if __name__ == "__main__":
    main()
