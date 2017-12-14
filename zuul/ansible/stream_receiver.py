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

import builtins
import logging
import io
import pickle
import socketserver
import struct
import threading


# RestrictedUnpickler derived from example Python docs at
# https://docs.python.org/3/library/pickle.html
class RestrictedUnpickler(pickle.Unpickler):
    _safe_builtins = {
        'str',
        'bytes',
        'dict',
        'list',
        'bool',
    }

    def find_class(self, module, name):
        """Limit attributes unpickled to minimal clases used in stream."""
        if module == "builtins" and name in self._safe_builtins:
            return getattr(builtins, name)
        raise pickle.UnpicklingError(
            "global '{module}.{name}' is forbidden".format(
                module=module,
                name=name))

    @classmethod
    def loads(cls, content):
        return cls(io.BytesIO(content)).load()


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        log = logging.getLogger('zuul.executor.ansible')
        log.info("Handle called")
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            # TODO(mordred) Investigate using either json or forwarding
            # a unix domain socket instead.
            obj = RestrictedUnpickler.loads(chunk)
            record = logging.makeLogRecord(obj)
            # TODO(mordred) Deal with ts= in the extras as well as adding
            # self.server.host to the front of the line.
            log.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    def __init__(self, host, task_name, port):
        self.log = logging.getLogger('zuul.executor.ansible')
        self.host = host
        self.task_name = task_name
        self.log.info("LogRecordSocketReceiver started")

        socketserver.ThreadingTCPServer.__init__(
            self, ('localhost', port), LogRecordStreamHandler)

        self.log.info("[%s] Starting to log for task %s", host, task_name)


class StreamReceiver(threading.Thread):

    def __init__(self, host=None, task_name=None, port=0):
        super(StreamReceiver, self).__init__(
            name='zuul-stream-{host}'.format(host=host))
        self.server = LogRecordSocketReceiver(
            host=host, task_name=task_name, port=port)

    def get_port(self):
        return self.server.socket.getsockname()[1]

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
