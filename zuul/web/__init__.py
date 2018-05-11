#!/usr/bin/env python
# Copyright (c) 2017 Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import cherrypy
import socket
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
import asyncio
import codecs
import copy
import json
import logging
import os
import time
import uvloop

import aiohttp
from aiohttp import web

import zuul.model
import zuul.rpcclient

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
WebSocketPlugin(cherrypy.engine).subscribe()
cherrypy.tools.websocket = WebSocketTool()


class ChangeFilter(object):
    def __init__(self, desired):
        self.desired = desired

    def filterPayload(self, payload):
        status = []
        for pipeline in payload['pipelines']:
            for change_queue in pipeline['change_queues']:
                for head in change_queue['heads']:
                    for change in head:
                        if self.wantChange(change):
                            status.append(copy.deepcopy(change))
        return status

    def wantChange(self, change):
        return change['id'] == self.desired


class LogStreamHandler(WebSocket):
    log = logging.getLogger("zuul.web")

    def received_message(self, message):
        if message.is_text:
            req = json.loads(message.data.decode('utf-8'))
            self.log.debug("Websocket request: %s", req)
            self._streamLog(req)

    def _streamLog(self, request):
        """
        Stream the log for the requested job back to the client.

        :param aiohttp.web.WebSocketResponse ws: The websocket response object.
        :param dict request: The client request parameters.
        """
        for key in ('uuid', 'logfile'):
            if key not in request:
                return (4000, "'{key}' missing from request payload".format(
                        key=key))

        port_location = self.rpc.get_job_log_stream_address(request['uuid'])
        if not port_location:
            return (4011, "Error with Gearman")

        self._fingerClient(
            port_location['server'], port_location['port'],
            request['uuid'])

        return (1000, "No more data")

    def _fingerClient(self, server, port, build_uuid):
        """
        Create a client to connect to the finger streamer and pull results.

        :param aiohttp.web.WebSocketResponse ws: The websocket response object.
        :param str server: The executor server running the job.
        :param str port: The executor server port.
        :param str build_uuid: The build UUID to stream.
        """
        self.log.debug("Connecting to finger server %s:%s", server, port)
        Decoder = codecs.getincrementaldecoder('utf8')
        decoder = Decoder()
        with socket.create_connection((server, port), timeout=10) as s:
            # timeout only on the connection, let recv() wait forever
            s.settimeout(None)
            msg = "%s\n" % build_uuid    # Must have a trailing newline!
            s.sendall(msg.encode('utf-8'))
            while True:
                data = s.recv(1024)
                if data:
                    data = decoder.decode(data)
                    if data:
                        self.send(data, False)
                else:
                    # Make sure we flush anything left in the decoder
                    data = decoder.decode(b'', final=True)
                    if data:
                        self.send(data, False)
                    self.close()
                    return


class ZuulWebAPI(object):
    log = logging.getLogger("zuul.web")

    def __init__(self, zuulweb):
        self.rpc = zuulweb.rpc
        self.zuulweb = zuulweb
        self.cache = {}
        self.cache_time = {}
        self.cache_expiry = 1

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def info(self):
        return self._handleInfo(self.zuulweb.info)

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def tenant_info(self, tenant):
        info = self.zuulweb.info.copy()
        info.tenant = tenant
        return self._handleInfo(info)

    def _handleInfo(self, info):
        ret = {'info': info.toDict()}
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        if self.static_cache_expiry:
            resp.headers['Cache-Control'] = "public, max-age=%d" % \
                self.static_cache_expiry
        resp.last_modified = self.zuulweb.start_time
        return ret

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def tenants(self):
        job = self.rpc.submitJob('zuul:tenant_list', {})
        ret = json.loads(job.data[0])
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def status(self, tenant):
        if tenant not in self.cache or \
           (time.time() - self.cache_time[tenant]) > self.cache_expiry:
            job = self.rpc.submitJob('zuul:status_get',
                                     {'tenant': tenant})
            self.cache[tenant] = json.loads(job.data[0])
            self.cache_time[tenant] = time.time()
        payload = self.cache[tenant]
        if payload.get('code') == 404:
            raise cherrypy.HTTPError(404, payload['message'])
        resp = cherrypy.response
        resp.headers["Cache-Control"] = "public, max-age=%d" % \
                                        self.cache_expiry
        resp.headers["Last-modified"] = self.cache_time[tenant]
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return payload

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def jobs(self, tenant):
        job = self.rpc.submitJob('zuul:job_list', {'tenant': tenant})
        ret = json.loads(job.data[0])
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def key_get(self, tenant, project):
        job = self.rpc.submitJob('zuul:key_get', {'tenant': tenant,
                                                  'project': project})
        ret = json.loads(job.data[0])
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.websocket(handler_cls=LogStreamHandler)
    def console_stream(self, tenant):
        cherrypy.request.ws_handler.rpc = self.rpc


class TenantStaticHandler(object):
    def __init__(self, path):
        self._cp_config = {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': path,
            'tools.staticdir.index': 'status.html',
            }


class RootStaticHandler(object):
    def __init__(self, path):
        self._cp_config = {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': path,
            'tools.staticdir.index': 'tenants.html',
            }


class ZuulWeb(object):
    log = logging.getLogger("zuul.web.ZuulWeb")

    def __init__(self, listen_address, listen_port,
                 gear_server, gear_port,
                 ssl_key=None, ssl_cert=None, ssl_ca=None,
                 static_cache_expiry=3600,
                 connections=None,
                 info=None,
                 static_path=None):
        self.start_time = time.time()
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.event_loop = None
        self.term = None
        self.server = None
        self.static_cache_expiry = static_cache_expiry
        self.info = info
        self.static_path = os.path.abspath(static_path or STATIC_DIR)
        # instanciate handlers
        self.rpc = zuul.rpcclient.RPCClient(gear_server, gear_port,
                                            ssl_key, ssl_cert, ssl_ca)
        self._plugin_routes = []  # type: List[zuul.web.handler.BaseWebHandler]
        self._connection_handlers = []
        connections = connections or []
        for connection in connections:
            self._connection_handlers.extend(
                connection.getWebHandlers(self, self.info))
        self._plugin_routes.extend(self._connection_handlers)

        route_map = cherrypy.dispatch.RoutesDispatcher()
        api = ZuulWebAPI(self)
        tenant_static = TenantStaticHandler(self.static_path)
        root_static = RootStaticHandler(self.static_path)
        route_map.connect('api', '/api/info',
                          controller=api, action='info')
        route_map.connect('api', '/api/tenants',
                          controller=api, action='tenants')
        route_map.connect('api', '/api/tenant/{tenant}/info',
                          controller=api, action='tenant_info')
        route_map.connect('api', '/api/tenant/{tenant}/status',
                          controller=api, action='status')
        route_map.connect('api', '/api/tenant/{tenant}/jobs',
                          controller=api, action='jobs')
        route_map.connect('api', '/api/tenant/{tenant}/key/{project:.*}.pub',
                          controller=api, action='jobs')
        route_map.connect('api', '/api/tenant/{tenant}/console-stream',
                          controller=api, action='console_stream')
        # Add fallthrough routes at the end for the static html/js files
        route_map.connect('root_static', '/{path:.*}',
                          controller=root_static)
        route_map.connect('tenant_static', '/t/{tenant}/{path:.*}',
                          controller=tenant_static)

        conf = {
            '/': {
                'request.dispatch': route_map
            }
        }
        cherrypy.config.update({
            'global': {
                'environment' : 'production',
                'server.socket_host': listen_address,
                'server.socket_port': listen_port,
            },
        })

        cherrypy.tree.mount(None, '/', config=conf)
        cherrypy.engine.start()

    @property
    def port(self):
        return cherrypy.server.bound_addr[1]

    async def _handleStatusChangeRequest(self, request):
        change = request.match_info["change"]
        return await self.gearman_handler.processRequest(
            request, 'status_get', ChangeFilter(change))

    async def _handleStatic(self, request):
        # http://example.com//status.html comes in as '/status.html'
        target_path = request.match_info['path'].lstrip('/')
        fs_path = os.path.abspath(os.path.join(self.static_path, target_path))
        if not fs_path.startswith(os.path.abspath(self.static_path)):
            return web.HTTPForbidden()
        if not os.path.exists(fs_path):
            return web.HTTPNotFound()
        return web.FileResponse(fs_path)

    def run(self, loop=None):
        """
        Run the websocket daemon.

        Because this method can be the target of a new thread, we need to
        set the thread event loop here, rather than in __init__().

        :param loop: The event loop to use. If not supplied, the default main
            thread event loop is used. This should be supplied if ZuulWeb
            is run within a separate (non-main) thread.
        """
        routes = [
            #('GET', '/api/tenant/{tenant}/status/change/{change}',
            # self._handleStatusChangeRequest),
        ]

        #for route in static_routes + self._plugin_routes:
        #    routes.append((route.method, route.path, route.handleRequest))

        self.log.debug("ZuulWeb starting")

    def stop(self):
        self.rpc.shutdown()
        cherrypy.engine.exit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    z = ZuulWeb(listen_address="127.0.0.1", listen_port=9000,
                gear_server="127.0.0.1", gear_port=4730)
    z.run()
    cherrypy.engine.block()
