# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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

import json
import logging
import threading
from paste import httpserver
from webob import Request

import zuul.rpcclient

# TODO: This should be implemented as an RPC client so that it has the
# possibility to be broken out from zuul.


class WebApp(threading.Thread):
    log = logging.getLogger("zuul.WebApp")

    def __init__(self, scheduler, port=8001):
        threading.Thread.__init__(self)
        self.scheduler = scheduler
        self.port = port

    def run(self):
        self.server = httpserver.serve(self.app, host='0.0.0.0',
                                       port=self.port, start_loop=False)
        self.server.serve_forever()

    def stop(self):
        self.server.server_close()

    def app(self, environ, start_response):
        request = Request(environ)
        if request.path == '/status.json':
            try:
                ret = self.scheduler.formatStatusJSON()
            except:
                self.log.exception("Exception formatting status:")
                raise
            start_response('200 OK', [('content-type', 'application/json'),
                                      ('Access-Control-Allow-Origin', '*')])
            return [ret]
        if request.path == '/metrics.json':
            # make an RPC to get the metrics, for now grab the gearman details
            # from the scheduler.
            # TODO: fix me once status.json is also an RPC (ie webapp should
            # have its own config to know where gearman is etc)
            server = self.scheduler.config.get('gearman', 'server')
            if self.scheduler.config.has_option('gearman', 'port'):
                port = self.scheduler.config.get('gearman', 'port')
            else:
                port = 4730
            try:
                client = zuul.rpcclient.RPCClient(server, port)
                ret = json.dumps(client.get_metrics())
            except Exception:
                self.log.exception("Exception getting metrics")
                raise

            start_response('200 OK', [('content-type', 'application/json'),
                                      ('Access-Control-Allow-Origin', '*')])

            return [ret]

        else:
            start_response('404 Not Found', [('content-type', 'text/plain')])
            return ['Not found.']
