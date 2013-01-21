# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

# So we can name this module "jenkins" and still load the "jenkins"
# system module

import json
import Queue
import threading
import zmq


class EventProxy(threading.Thread):
    def __init__(self, proxy_port='8002'):
        self.proxy_port = proxy_port
        self.event_queue = Queue.Queue()

    def addEvent(self, event):
        self.event_queue.put(event)

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.bind("tcp://*:%s" % self.proxy_port)
        while True:
            event = self.event_queue.get()
            socket.send("%s %s" % (event['build']['phase'], json.dumps(event)))
