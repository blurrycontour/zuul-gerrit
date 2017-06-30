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

import asyncio
import copy
import json
import logging
import threading
import time
import uvloop

from aiohttp import web

from zuul.lib import encryption

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
                 listen_address='0.0.0.0', loop=None):
        threading.Thread.__init__(self)
        self.scheduler = scheduler
        self.listen_address = listen_address
        self.port = port
        self.cache_expiry = cache_expiry
        self.cache_time = 0
        self.cache = {}
        self.daemon = True
        self.routes = {}
        self._finished = False

        # Set up aiohttp
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        self.user_supplied_loop = loop is not None
        if not loop:
            loop = asyncio.get_event_loop()
        self.event_loop = loop
        asyncio.set_event_loop(loop)
        self._register_default_routes()

    def _register_default_routes(self):
        self.registerPath(
                'GET', '/status/change/{change}', self.handle_change)
        self.registerPath(
                'GET', '/status', self.handle_status)
        self.registerPath(
                'GET', '/keys/{connection}/{project}.pub', self.handle_keys)

    def run(self):
        while not self._finished:
            self.app = self._create_application()

            handler = self.app.make_handler(loop=self.event_loop)
            coro = self.event_loop.create_server(handler,
                                                 self.listen_address,
                                                 self.port)
            self.server = self.event_loop.run_until_complete(coro)
            self.term = asyncio.Future()

            self.event_loop.run_until_complete(self.term)

            # cleanup
            self.server.close()
            self.event_loop.run_until_complete(self.server.wait_closed())
            self.event_loop.run_until_complete(self.app.shutdown())
            self.event_loop.run_until_complete(handler.shutdown(60.0))
            self.event_loop.run_until_complete(self.app.cleanup())
            self.app = None

        # Only run these if we are controlling the loop - they need to be
        # run from the main thread
        if not self.user_supplied_loop:
            self.event_loop.stop()
            self.event_loop.close()

    def stop(self):
        self._finished = True
        self.event_loop.call_soon_threadsafe(self.term.set_result, True)
        await self.server.wait_closed()

    def restart(self):
        self.event_loop.call_soon_threadsafe(self.term.set_result, True)

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

    def _makePathAndKey(self, path, tenant)
        # TODO(mordred) this is currently registering both on the root
        # and with a tenant argument - I think the desire is to stop having
        # the tenant argument be a thing.
        if not path.startswith('/'):
            path = '/' + path
        if tenant:
            path '/{tenant}' + path
        key = method + path
        return key, path

    def registerPath(self, method, path, handler, tenant):
        path, key = self._makePathAndKey(path, tenant)
        if key not in self.routes:
            self.routes[key] = (method, path, handler)
            if self.app:
                self.restart()

    def unregisterPath(self, method, path, handler, tenant):
        path, key = self._tenantityPath(path, tenant)
        if key in self.routes:
            del self.routes[key]
            if self.app:
                self.restart()

    def _create_application(self):
        app = web.Application()
        for path, (method, handler) in self.routes.items()
            app.add_route(method, '/{tenant}' + path, handler)
            app.add_route(method, path, handler)
        return app

    def handle_keys(self, request):
        connection_name = request.match_info['connection']
        project_name = request.match_info['project']
        source = self.scheduler.connections.getSource(connection_name)
        if not source:
            raise web.HTTPNotFound()
        project = source.getProject(project_name)
        if not project:
            raise web.HTTPNotFound()

        pem_public_key = encryption.serialize_rsa_public_key(
            project.public_key)

        return web.Response(body=pem_public_key,
                            content_type='text/plain')

    def handle_status(self, request):
        tenant_name = request.match_info['tenant']
        def func():
            return web.Response(body=self.cache[tenant_name],
                                content_type='application/json',
                                charset='utf8')
        return self._response_with_status_cache(func, tenant_name)

    def handle_change(self, request):
        def func():
            change_id = request.match_info.get('tenant', '')
            status = self._status_for_change(change_id, tenant_name)
            if status:
                return web.Response(body=status,
                                    content_type='application/json',
                                    charset='utf8')
            else:
                return web.Response(status=404)
        return self._response_with_status_cache(func, tenant_name)

    def _refresh_status_cache(self, tenant_name):
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

    def _response_with_status_cache(self, func, tenant_name):
        self._refresh_status_cache(tenant_name)

        response = func()

        response.add_header('Access-Control-Allow-Origin', '*')
        response.add_header(
            'Cache-Control',
            'public, max-age={age}'.format(age=self.cache_expiry))
        response.last_Modified = self.cache_time

        # TODO(mordred) Double-check format of these. Also, max-age is
        # supposed to take precedence, so do we need to send this one?
        # response.add_header('Expires', self.cache_time + self.cache_expiry)

        return response
