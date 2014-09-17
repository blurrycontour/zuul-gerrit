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

import cgi
import logging
import threading
import time
from paste import httpserver
import webob
from webob import dec


class WebApp(threading.Thread):
    log = logging.getLogger("zuul.WebApp")

    def __init__(self, scheduler, port=8001, cache_expiry=1):
        threading.Thread.__init__(self)
        self.scheduler = scheduler
        self.port = port
        self.cache_expiry = cache_expiry
        self.cache_time = 0
        self.cache = None
        self.daemon = True
        self.server = httpserver.serve(dec.wsgify(self.app), host='0.0.0.0',
                                       port=self.port, start_loop=False)

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.server_close()

    def app(self, request):
        if request.path != '/status.json':
            raise webob.exc.HTTPNotFound()

        change_filter = None
        parameters = cgi.parse_qs(request.query_string)
        if 'change_filter' in parameters:
            change_filter = cgi.escape(parameters['change_filter'][0])

        update_cache = False
        if (not self.cache or
            (time.time() - self.cache_time) > self.cache_expiry):
            update_cache = True

        if update_cache or change_filter:
            try:
                status_json = self.scheduler.formatStatusJSON(change_filter)
            except:
                self.log.exception("Exception formatting status:")
                raise
            if update_cache:
                self.cache = status_json
                # Call time.time() again because formatting above may take
                # longer than the cache timeout.
                self.cache_time = time.time()
        else:
            status_json = self.cache

        response = webob.Response(body=status_json,
                                  content_type='application/json')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.last_modified = self.cache_time
        return response
