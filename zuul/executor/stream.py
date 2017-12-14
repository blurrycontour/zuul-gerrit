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

from zuul.ansible import logconfig


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
    def __init__(self, *args, **kwargs):
        self.logname = self.server.logname
        self.log = logging.getLogger(self.logname)
        self.log.info("Handler created")
        self._applyLoggingConfig()
        super(LogRecordStreamHandler, self).__init__(*args, **kwargs)

    def _applyLoggingConfig(self):
        """Apply logging config for this stream.

        Logging config in python is global, but we're logging each
        job to a different file. We need to apply an incremental update
        to the logging config and emit the messages to the logger named
        for the LogStreamer thread.
        """
        logging_config = logconfig.StreamLoggingConfig(
            job_output_file=self.server.logfile,
            logname=self.server.logname)
        logging_config.apply()

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        self.log.info("handle called")
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
            self.logger.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    def __init__(self, logname, logfile, port):
        self.log = logging.getLogger(logname)
        self.log.info("LogRecordSocketReceiver started")
        socketserver.ThreadingTCPServer.__init__(
            self, ('localhost', port), LogRecordStreamHandler)

        self.logname = logname
        self.logfile = logfile


class LogStreamer(threading.Thread):

    def __init__(self, uuid, logfile, port=0):
        name = 'zuul-log-stream-%s' % uuid
        super(LogStreamer, self).__init__(name=name)
        self.server = LogRecordSocketReceiver(
            logname=name, logfile=logfile, port=port)

    def get_port(self):
        return self.server.socket.getsockname()[1]

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
