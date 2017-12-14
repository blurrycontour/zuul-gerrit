# Copyright 2018 Red Hat, Inc.
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
import json
import socketserver
import struct
import threading


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in json format. Logs the record
        according to whatever policy is configured locally.
        """
        log = logging.getLogger('zuul.executor.ansible')
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = json.loads(chunk.decode('utf-8'))
            if obj['levelno'] is None:
                continue
            record = logging.makeLogRecord(obj)
            record.msg = '%s | %s | %s' % (
                record.ts, self.server.host, record.msg)
            # TODO(mordred) Deal with ts= in the extras as well as adding
            # self.server.host to the front of the line.
            log.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    def __init__(self, host, port):
        self.host = host
        socketserver.ThreadingTCPServer.__init__(
            self, ('localhost', port), LogRecordStreamHandler)


class StreamReceiver(threading.Thread):

    def __init__(self, host=None, port=0):
        super(StreamReceiver, self).__init__(
            name='zuul-stream-{host}'.format(host=host))
        self.server = LogRecordSocketReceiver(host=host, port=port)

    def get_port(self):
        return self.server.socket.getsockname()[1]

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
