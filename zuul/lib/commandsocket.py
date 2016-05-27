# Copyright 2014 OpenStack Foundation
# Copyright 2014 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Red Hat
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
import os
import socket
import threading
import Queue


class CommandSocket(object):
    log = logging.getLogger("zuul.CommandSocket")

    def __init__(self, path):
        self.path = path
        self.queue = Queue.Queue()

    def start(self):
        if os.path.exists(self.path):
            os.unlink(self.path)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(self.path)
        self.socket.listen(1)
        self.socket_thread = threading.Thread(target=self._socketListener)
        self.socket_thread.daemon = True
        self.socket_thread.start()

    def stop(self):
        # This is primarily for the benefit of users of this class.
        # Because the .get() method blocks indefinitely, putting a
        # something on the queue will cause that to return allowing
        # the waiting thread to exit cleanly.
        # TODO: make an internal connection to the socket to escape
        # the accept method and actually stop the listener.
        self.queue.put('_stop')

    def _socketListener(self):
        while True:
            try:
                s, addr = self.socket.accept()
                self.log.debug("Accepted socket connection %s" % (s,))
                buf = ''
                while True:
                    buf += s.recv(1)
                    if buf[-1] == '\n':
                        break
                buf = buf.strip()
                self.log.debug("Received %s from socket" % (buf,))
                s.close()
                # Because we use '_stop' internally to wake up a
                # waiting thread, don't allow it to actually be
                # injected externally.
                if buf != '_stop':
                    self.queue.put(buf)
            except Exception:
                self.log.exception("Exception in socket handler")

    def get(self):
        # TODO: if we have stopped, refuse further calls here.
        return self.queue.get()
