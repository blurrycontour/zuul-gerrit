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

import copy
import json
import logging
import re
import threading
import time
from paste import httpserver
import webob
from webob import dec
from cryptography.hazmat.primitives import serialization

"""Zuul main web app.

Zuul supports HTTP requests directly against it for determining the
change status. These responses are provided as json data structures.

The supported urls are:

 - /status: return a complex data structure that represents the entire
   queue / pipeline structure of the system
 - /status.json (backwards compatibility): same as /status
 - /status/change/X,Y: return status just for gerrit change X,Y
 - /keys/SOURCE/PROJECT.pub: return the public key for PROJECT

When returning status for a single gerrit change you will get an
array of changes, they will not include the queue structure.
"""


class WebApp(threading.Thread):
    log = logging.getLogger("zuul.WebApp")

    def __init__(self, scheduler, port=8001, cache_expiry=1,
                 listen_address='0.0.0.0'):
        threading.Thread.__init__(self)
        self.scheduler = scheduler
        self.listen_address = listen_address
        self.port = port
        self.cache_expiry = cache_expiry
        self.cache_time = 0
        self.cache = {}
        self.daemon = True
        self.server = httpserver.serve(
            dec.wsgify(self.app), host=self.listen_address, port=self.port,
            start_loop=False)

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.server_close()

    def _changes_by_func(self, func, tenant_name):
        """Filter changes by a user provided function.

        In order to support arbitrary collection of subsets of changes
        we provide a low level filtering mechanism that takes a
        function which applies to changes. The output of this function
        is a flattened list of those collected changes.
        """
        status = []
        jsonstruct = json.loads(self.cache[tenant_name])
        for pipeline in jsonstruct['pipelines']:
            for change_queue in pipeline['change_queues']:
                for head in change_queue['heads']:
                    for change in head:
                        if func(change):
                            status.append(copy.deepcopy(change))
        return json.dumps(status)

    def _status_for_change(self, rev, tenant_name):
        """Return the statuses for a particular change id X,Y."""
        def func(change):
            return change['id'] == rev
        return self._changes_by_func(func, tenant_name)

    def _normalize_path(self, path):
        # support legacy status.json as well as new /status
        if path == '/status.json' or path == '/status':
            return "status"
        m = re.match('/status/change/(\d+,\d+)$', path)
        if m:
            return m.group(1)
        return None

    def _handle_keys(self, request, path):
        m = re.match('/keys/(.*?)/(.*?).pub', path)
        source_name = m.group(1)
        project_name = m.group(2)
        source = self.scheduler.connections.getSource(source_name)
        project = source.getProject(project_name)

        # Serialize public key
        pem_public_key = project.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        response = webob.Response(body=pem_public_key,
                                  content_type='text/plain')
        return response.conditional_response_app

    def app(self, request):
        tenant_name = request.path.split('/')[1]
        path = request.path.replace('/' + tenant_name, '')
        if path.startswith('/keys'):
            return self._handle_keys(request, path)
        path = self._normalize_path(path)
        if path is None:
            raise webob.exc.HTTPNotFound()

        if (tenant_name not in self.cache or
            (time.time() - self.cache_time) > self.cache_expiry):
            try:
                self.cache[tenant_name] = self.scheduler.formatStatusJSON(
                    tenant_name)
                # Call time.time() again because formatting above may take
                # longer than the cache timeout.
                self.cache_time = time.time()
            except:
                self.log.exception("Exception formatting status:")
                raise

        if path == 'status':
            response = webob.Response(body=self.cache[tenant_name],
                                      content_type='application/json')
        else:
            status = self._status_for_change(path, tenant_name)
            if status:
                response = webob.Response(body=status,
                                          content_type='application/json')
            else:
                raise webob.exc.HTTPNotFound()

        response.headers['Access-Control-Allow-Origin'] = '*'

        response.cache_control.public = True
        response.cache_control.max_age = self.cache_expiry
        response.last_modified = self.cache_time
        response.expires = self.cache_time + self.cache_expiry

        return response.conditional_response_app
