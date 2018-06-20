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
import jwt
import socket
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
import codecs
import copy
from datetime import datetime
import json
import logging
import math
import os
import time
import select
import threading

import zuul.model
import zuul.rpcclient

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
cherrypy.tools.websocket = WebSocketTool()


class SaveParamsTool(cherrypy.Tool):
    """
    Save the URL parameters to allow them to take precedence over query
    string parameters.
    """
    def __init__(self):
        cherrypy.Tool.__init__(self, 'on_start_resource',
                               self.saveParams)

    def _setup(self):
        cherrypy.Tool._setup(self)
        cherrypy.request.hooks.attach('before_handler',
                                      self.restoreParams)

    def saveParams(self, restore=True):
        cherrypy.request.url_params = cherrypy.request.params.copy()
        cherrypy.request.url_params_restore = restore

    def restoreParams(self):
        if cherrypy.request.url_params_restore:
            cherrypy.request.params.update(cherrypy.request.url_params)


cherrypy.tools.save_params = SaveParamsTool()


@cherrypy.tools.register('before_handler')
def unprotected():
    """Remove JWT token if present in the query string, as it interferes with
    routing when it is not needed.
    This will allow to indiscriminately inject JWTs with a HTTPd rewrite rule
    and let the HTTP server handle token fetching."""
    params = cherrypy.request.params
    if 'jwt' in params:
        del params['jwt']


@cherrypy.tools.register('before_handler')
def protected():
    """Protect admin endpoints:
    - HTTP 403 (Forbidden) if the admin endpoints are disabled
    - HTTP 401 (Unauthorized) if the request is made without a valid JWT.

    The JWT is expected to be of the form:
    {'exp': <timestamp>,
     'zuul.tenants': {'tenantA': ['projectA', 'projectB'],
                      'tenantB': '*'}
    }
    Bearing such a token allows privileged actions on projectA and projectB for
    tenantA, and on every project of tenantB, until timestamp.
    """
    enabled = cherrypy.request.app.config['authZ']['enabled']
    JWTsecret = cherrypy.request.app.config['authZ']['JWTsecret']
    JWTalgorithm = cherrypy.request.app.config['authZ']['JWTalgorithm']
    if not enabled:
        raise cherrypy.HTTPError(403, 'The admin endpoints are disabled')
    params = cherrypy.request.params
    # look for the token: either in headers or as a URL param
    token = cherrypy.request.headers.get('Authorization', None)
    if token is None:
        if 'jwt' in params:
            token = params['jwt']
            del params['jwt']
    else:
        if not token.lower().startswith('bearer '):
            raise cherrypy.HTTPError(401,
                                     'Authorization with bearer token '
                                     'required')
        token = token[len('bearer '):]
    if token is None:
        raise cherrypy.HTTPError(401,
                                 'Authorization with bearer token '
                                 'required')
    try:
        decoded = jwt.decode(token, JWTsecret,
                             algorithms=JWTalgorithm)
    except jwt.DecodeError:
        raise cherrypy.HTTPError(401,
                                 'The bearer token could not be decoded')
    except jwt.exceptions.ExpiredSignatureError:
        raise cherrypy.HTTPError(401,
                                 'The bearer token has expired')
    # If not caught
    expires = decoded.get('exp', math.inf)
    if expires < time.time():
        raise cherrypy.HTTPError(401,
                                 'The bearer token has expired')

    zuul_tenants = decoded.get('zuul.tenants', {})
    if not isinstance(zuul_tenants, dict):
        raise cherrypy.HTTPError(400,
                                 'invalid zuul.tenants claim')
    if 'tenant' in params:
        if params['tenant'] not in zuul_tenants.keys():
            raise cherrypy.HTTPError(401,
                                     'You are not allowed privileged '
                                     'actions on this tenant')
        allowed_projects = zuul_tenants[params['tenant']]
        if not isinstance(allowed_projects, list) and allowed_projects != '*':
            raise cherrypy.HTTPError(400,
                                     'invalid zuul.tenants claim')
        if 'project' in params:
            is_allowed = (allowed_projects == '*' or
                          params['project'] in allowed_projects)
        else:
            is_allowed = (allowed_projects == '*')
        if not is_allowed:
            raise cherrypy.HTTPError(401,
                                     'You are not allowed privileged '
                                     'actions on this tenant and/or project')
    else:
        # Since all admin actions are at least tenant scoped, the tenant
        # should be there
        raise cherrypy.HTTPError(403,
                                 'This operation must be scoped '
                                 'to a tenant')


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

    def __init__(self, *args, **kw):
        kw['heartbeat_freq'] = 20
        super(LogStreamHandler, self).__init__(*args, **kw)
        self.streamer = None

    def received_message(self, message):
        if message.is_text:
            req = json.loads(message.data.decode('utf-8'))
            self.log.debug("Websocket request: %s", req)
            if self.streamer:
                self.log.debug("Ignoring request due to existing streamer")
                return
            try:
                self._streamLog(req)
            except Exception:
                self.log.exception("Error processing websocket message:")
                raise

    def closed(self, code, reason=None):
        self.log.debug("Websocket closed: %s %s", code, reason)
        if self.streamer:
            try:
                self.streamer.zuulweb.stream_manager.unregisterStreamer(
                    self.streamer)
            except Exception:
                self.log.exception("Error on remote websocket close:")

    def logClose(self, code, msg):
        self.log.debug("Websocket close: %s %s", code, msg)
        try:
            self.close(code, msg)
        except Exception:
            self.log.exception("Error closing websocket:")

    def _streamLog(self, request):
        """
        Stream the log for the requested job back to the client.

        :param dict request: The client request parameters.
        """
        for key in ('uuid', 'logfile'):
            if key not in request:
                return self.logClose(
                    4000,
                    "'{key}' missing from request payload".format(
                        key=key))

        port_location = self.zuulweb.rpc.get_job_log_stream_address(
            request['uuid'])
        if not port_location:
            return self.logClose(4011, "Error with Gearman")

        self.streamer = LogStreamer(
            self.zuulweb, self,
            port_location['server'], port_location['port'],
            request['uuid'])


class LogStreamer(object):
    log = logging.getLogger("zuul.web")

    def __init__(self, zuulweb, websocket, server, port, build_uuid):
        """
        Create a client to connect to the finger streamer and pull results.

        :param str server: The executor server running the job.
        :param str port: The executor server port.
        :param str build_uuid: The build UUID to stream.
        """
        self.log.debug("Connecting to finger server %s:%s", server, port)
        Decoder = codecs.getincrementaldecoder('utf8')
        self.decoder = Decoder()
        self.finger_socket = socket.create_connection(
            (server, port), timeout=10)
        self.finger_socket.settimeout(None)
        self.websocket = websocket
        self.zuulweb = zuulweb
        self.uuid = build_uuid
        msg = "%s\n" % build_uuid    # Must have a trailing newline!
        self.finger_socket.sendall(msg.encode('utf-8'))
        self.zuulweb.stream_manager.registerStreamer(self)

    def __repr__(self):
        return '<LogStreamer %s uuid:%s>' % (self.websocket, self.uuid)

    def errorClose(self):
        self.websocket.logClose(4011, "Unknown error")

    def handle(self, event):
        if event & select.POLLIN:
            data = self.finger_socket.recv(1024)
            if data:
                data = self.decoder.decode(data)
                if data:
                    self.websocket.send(data, False)
            else:
                # Make sure we flush anything left in the decoder
                data = self.decoder.decode(b'', final=True)
                if data:
                    self.websocket.send(data, False)
                self.zuulweb.stream_manager.unregisterStreamer(self)
                return self.websocket.logClose(1000, "No more data")
        else:
            self.zuulweb.stream_manager.unregisterStreamer(self)
            return self.websocket.logClose(1000, "Remote error")


class ZuulWebAPI(object):
    log = logging.getLogger("zuul.web")

    def __init__(self, zuulweb):
        self.rpc = zuulweb.rpc
        self.zuulweb = zuulweb
        self.cache = {}
        self.cache_time = {}
        self.cache_expiry = 1
        self.static_cache_expiry = zuulweb.static_cache_expiry

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def info(self):
        return self._handleInfo(self.zuulweb.info)

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
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
    @cherrypy.tools.unprotected()
    def tenants(self):
        job = self.rpc.submitJob('zuul:tenant_list', {})
        ret = json.loads(job.data[0])
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    def _getStatus(self, tenant):
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
        last_modified = datetime.utcfromtimestamp(self.cache_time[tenant])
        last_modified_header = last_modified.strftime('%a, %d %b %Y %X GMT')
        resp.headers["Last-modified"] = last_modified_header
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return payload

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def status(self, tenant):
        return self._getStatus(tenant)

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def status_change(self, tenant, change):
        payload = self._getStatus(tenant)
        result_filter = ChangeFilter(change)
        return result_filter.filterPayload(payload)

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def jobs(self, tenant):
        job = self.rpc.submitJob('zuul:job_list', {'tenant': tenant})
        ret = json.loads(job.data[0])
        if ret is None:
            raise cherrypy.HTTPError(404, 'Tenant %s does not exist.' % tenant)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def config_errors(self, tenant):
        config_errors = self.rpc.submitJob(
            'zuul:config_errors_list', {'tenant': tenant})
        ret = json.loads(config_errors.data[0])
        if ret is None:
            raise cherrypy.HTTPError(404, 'Tenant %s does not exist.' % tenant)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def job(self, tenant, job_name):
        job = self.rpc.submitJob(
            'zuul:job_get', {'tenant': tenant, 'job': job_name})
        ret = json.loads(job.data[0])
        if not ret:
            raise cherrypy.HTTPError(404, 'Job %s does not exist.' % job_name)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.unprotected()
    def key(self, tenant, project):
        job = self.rpc.submitJob('zuul:key_get', {'tenant': tenant,
                                                  'project': project,
                                                  'key': 'secrets'})
        if not job.data:
            raise cherrypy.HTTPError(
                404, 'Project %s does not exist.' % project)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Content-Type'] = 'text/plain'
        return job.data[0]

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.unprotected()
    def project_ssh_key(self, tenant, project):
        job = self.rpc.submitJob('zuul:key_get', {'tenant': tenant,
                                                  'project': project,
                                                  'key': 'ssh'})
        if not job.data:
            raise cherrypy.HTTPError(
                404, 'Project %s does not exist.' % project)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Content-Type'] = 'text/plain'
        return job.data[0] + '\n'

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.unprotected()
    def builds(self, tenant, project=None, pipeline=None, change=None,
               branch=None, patchset=None, ref=None, newrev=None,
               uuid=None, job_name=None, voting=None, node_name=None,
               result=None, limit=50, skip=0):
        # Ask the scheduler which sql connection to use for this tenant
        job = self.rpc.submitJob('zuul:tenant_sql_connection',
                                 {'tenant': tenant})
        connection_name = json.loads(job.data[0])

        if not connection_name:
            raise cherrypy.HTTPError(404, 'Tenant %s does not exist.' % tenant)

        connection = self.zuulweb.connections.connections[connection_name]

        args = {
            'buildset_filters': {'tenant': [tenant]},
            'build_filters': {},
            'limit': limit,
            'skip': skip,
        }

        for k in ("project", "pipeline", "change", "branch",
                  "patchset", "ref", "newrev"):
            v = locals()[k]
            if v:
                args['buildset_filters'].setdefault(k, []).append(v)
        for k in ("uuid", "job_name", "voting", "node_name",
                  "result"):
            v = locals()[k]
            if v:
                args['build_filters'].setdefault(k, []).append(v)
        data = connection.get_builds(args)
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return data

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def build(self, tenant, uuid):
        # Ask the scheduler which sql connection to use for this tenant
        job = self.rpc.submitJob('zuul:tenant_sql_connection',
                                 {'tenant': tenant})
        connection_name = json.loads(job.data[0])

        if not connection_name:
            raise cherrypy.HTTPError(404, 'Tenant %s does not exist.' % tenant)

        connection = self.zuulweb.connections.connections[connection_name]

        args = {
            'buildset_filters': {'tenant': [tenant]},
            'build_filters': {'uuid': [uuid]},
            'limit': 1,
            'skip': 0,
        }
        data = connection.get_builds(args)
        if not data:
            raise cherrypy.HTTPError(404, "Build not found")
        data = data[0]
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return data

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.websocket(handler_cls=LogStreamHandler)
    @cherrypy.tools.unprotected()
    def console_stream(self, tenant):
        cherrypy.request.ws_handler.zuulweb = self.zuulweb

    @cherrypy.expose
    @cherrypy.tools.protected()
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def dequeue(self, tenant, project):
        if cherrypy.request.method != 'POST':
            raise cherrypy.HTTPError(405)
        body = cherrypy.request.json
        if 'pipeline' in body and (
            ('change' in body and 'ref' not in body) or
            ('change' not in body and 'ref' in body)):
            job = self.rpc.submitJob('zuul:dequeue',
                                     {'tenant': tenant,
                                      'pipeline': body['pipeline'],
                                      'project': project,
                                      'change': body.get('change', None),
                                      'ref': body.get('ref', None)})
            result = not job.failure
            resp = cherrypy.response
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return result
        else:
            raise cherrypy.HTTPError(400,
                                     'Invalid request body')

    @cherrypy.expose
    @cherrypy.tools.protected()
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def enqueue(self, tenant, project):
        if cherrypy.request.method != 'POST':
            raise cherrypy.HTTPError(405)
        body = cherrypy.request.json
        if all(p in body for p in ['trigger', 'change', 'pipeline']):
            return self._enqueue(tenant, project, **body)
        elif all(p in body for p in ['trigger', 'ref', 'oldrev',
                                     'newrev', 'pipeline']):
            return self._enqueue_ref(tenant, project, **body)
        else:
            raise cherrypy.HTTPError(400,
                                     'Invalid request body')

    def _enqueue(self, tenant, project, trigger, change, pipeline, **kwargs):
        job = self.rpc.submitJob('zuul:enqueue',
                                 {'tenant': tenant,
                                  'pipeline': pipeline,
                                  'project': project,
                                  'trigger': trigger,
                                  'change': change, })
        result = not job.failure
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return result

    def _enqueue_ref(self, tenant, project, trigger, ref,
                     oldrev, newrev, pipeline, **kwargs):
        job = self.rpc.submitJob('zuul:enqueue_ref',
                                 {'tenant': tenant,
                                  'pipeline': pipeline,
                                  'project': project,
                                  'trigger': trigger,
                                  'ref': ref,
                                  'oldrev': oldrev,
                                  'newrev': newrev, })
        result = not job.failure
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return result

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def autohold_list(self, tenant, *args, **kwargs):
        # we don't use json_in because a payload is not mandatory with GET
        if cherrypy.request.method != 'GET':
            raise cherrypy.HTTPError(405)
        # filter by project if passed as a query string
        project = cherrypy.request.params.get('project', None)
        return self._autohold_list(tenant, project)

    @cherrypy.expose
    @cherrypy.tools.protected()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def autohold(self, tenant, project=None):
        # we don't use json_in because a payload is not mandatory with GET
        # Note: GET handling is redundant with autohold_list
        # and could be removed.
        if cherrypy.request.method == 'GET':
            return self._autohold_list(tenant, project)
        elif cherrypy.request.method == 'POST':
            length = int(cherrypy.request.headers['Content-Length'])
            body = cherrypy.request.body.read(length)
            try:
                jbody = json.loads(body.decode('utf-8'))
            except ValueError:
                raise cherrypy.HTTPError(406, 'JSON body required')
            if (jbody.get('change') and jbody.get('ref')):
                raise cherrypy.HTTPError(400,
                                         'change and ref are '
                                         'mutually exclusive')
            else:
                jbody['change'] = jbody.get('change', None)
                jbody['ref'] = jbody.get('ref', None)
            if all(p in jbody for p in ['job', 'change', 'ref',
                                        'count', 'reason',
                                        'node_hold_expiration']):
                data = {'tenant': tenant,
                        'project': project,
                        'job': jbody['job'],
                        'change': jbody['change'],
                        'ref': jbody['ref'],
                        'reason': jbody['reason'],
                        'count': jbody['count'],
                        'node_hold_expiration': jbody['node_hold_expiration']}
                result = self.rpc.submitJob('zuul:autohold', data)
                return not result.failure
            else:
                raise cherrypy.HTTPError(400,
                                         'Invalid request body')
        else:
            raise cherrypy.HTTPError(405)

    def _autohold_list(self, tenant, project=None):
        job = self.rpc.submitJob('zuul:autohold_list', {})
        if job.failure:
            raise cherrypy.HTTPError(500, 'autohold-list failed')
        else:
            payload = json.loads(job.data[0])
            result = []
            for key in payload:
                _tenant, _project, job, ref_filter = key.split(',')
                count, reason, hold_expiration = payload[key]
                if tenant == _tenant:
                    if project is None or _project.endswith(project):
                        result.append(
                            {'tenant': _tenant,
                             'project': _project,
                             'job': job,
                             'ref_filter': ref_filter,
                             'count': count,
                             'reason': reason,
                             'node_hold_expiration': hold_expiration})
            return result


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


class StreamManager(object):
    log = logging.getLogger("zuul.web")

    def __init__(self):
        self.streamers = {}
        self.poll = select.poll()
        self.bitmask = (select.POLLIN | select.POLLERR |
                        select.POLLHUP | select.POLLNVAL)
        self.wake_read, self.wake_write = os.pipe()
        self.poll.register(self.wake_read, self.bitmask)

    def start(self):
        self._stopped = False
        self.thread = threading.Thread(
            target=self.run,
            name='StreamManager')
        self.thread.start()

    def stop(self):
        self._stopped = True
        os.write(self.wake_write, b'\n')
        self.thread.join()

    def run(self):
        while True:
            for fd, event in self.poll.poll():
                if self._stopped:
                    return
                if fd == self.wake_read:
                    os.read(self.wake_read, 1024)
                    continue
                streamer = self.streamers.get(fd)
                if streamer:
                    try:
                        streamer.handle(event)
                    except Exception:
                        self.log.exception("Error in streamer:")
                        streamer.errorClose()
                        self.unregisterStreamer(streamer)
                else:
                    try:
                        self.poll.unregister(fd)
                    except KeyError:
                        pass

    def registerStreamer(self, streamer):
        self.log.debug("Registering streamer %s", streamer)
        self.streamers[streamer.finger_socket.fileno()] = streamer
        self.poll.register(streamer.finger_socket.fileno(), self.bitmask)
        os.write(self.wake_write, b'\n')

    def unregisterStreamer(self, streamer):
        self.log.debug("Unregistering streamer %s", streamer)
        try:
            self.poll.unregister(streamer.finger_socket)
        except KeyError:
            pass
        try:
            del self.streamers[streamer.finger_socket.fileno()]
        except KeyError:
            pass


class ZuulWeb(object):
    log = logging.getLogger("zuul.web.ZuulWeb")

    def __init__(self, listen_address, listen_port,
                 gear_server, gear_port,
                 ssl_key=None, ssl_cert=None, ssl_ca=None,
                 static_cache_expiry=3600,
                 connections=None,
                 info=None,
                 static_path=None,
                 enable_admin_endpoints=False,
                 JWTsecret=None):
        self.start_time = time.time()
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.event_loop = None
        self.term = None
        self.server = None
        self.static_cache_expiry = static_cache_expiry
        self.info = info
        self.static_path = os.path.abspath(static_path or STATIC_DIR)
        self.enable_admin_endpoints = enable_admin_endpoints
        # TODO(mhu) For now, use HS256 (hardcoded) but this should be a setting
        self.JWTalgorithm = 'HS256'
        self.JWTsecret = JWTsecret
        # instanciate handlers
        self.rpc = zuul.rpcclient.RPCClient(gear_server, gear_port,
                                            ssl_key, ssl_cert, ssl_ca)
        self.connections = connections
        self.stream_manager = StreamManager()

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
        route_map.connect('api', '/api/tenant/{tenant}/status/change/{change}',
                          controller=api, action='status_change')
        route_map.connect('api', '/api/tenant/{tenant}/jobs',
                          controller=api, action='jobs')
        route_map.connect('api', '/api/tenant/{tenant}/job/{job_name}',
                          controller=api, action='job')
        route_map.connect('api', '/api/tenant/{tenant}/key/{project:.*}.pub',
                          controller=api, action='key')
        route_map.connect('api', '/api/tenant/{tenant}/'
                          'project-ssh-key/{project:.*}.pub',
                          controller=api, action='project_ssh_key')
        route_map.connect('api',
                          '/api/tenant/{tenant}/project/{project:.*}/autohold',
                          controller=api, action='autohold')
        route_map.connect('api', '/api/tenant/{tenant}/autohold',
                          controller=api, action='autohold_list')
        route_map.connect('api',
                          '/api/tenant/{tenant}/project/{project:.*}/enqueue',
                          controller=api, action='enqueue')
        route_map.connect('api',
                          '/api/tenant/{tenant}/project/{project:.*}/dequeue',
                          controller=api, action='dequeue')
        route_map.connect('api', '/api/tenant/{tenant}/console-stream',
                          controller=api, action='console_stream')
        route_map.connect('api', '/api/tenant/{tenant}/builds',
                          controller=api, action='builds')
        route_map.connect('api', '/api/tenant/{tenant}/build/{uuid}',
                          controller=api, action='build')
        route_map.connect('api', '/api/tenant/{tenant}/config-errors',
                          controller=api, action='config_errors')

        for connection in connections.connections.values():
            controller = connection.getWebController(self)
            if controller:
                cherrypy.tree.mount(
                    controller,
                    '/api/connection/%s' % connection.connection_name)

        # Add fallthrough routes at the end for the static html/js files
        route_map.connect('root_static', '/{path:.*}',
                          controller=root_static, action='default')
        route_map.connect('tenant_static', '/t/{tenant}/{path:.*}',
                          controller=tenant_static, action='default')

        conf = {
            '/': {
                'request.dispatch': route_map
            },
            'authZ': {
                'enabled': self.enable_admin_endpoints,
                'JWTsecret': self.JWTsecret,
                'JWTalgorithm': self.JWTalgorithm,
            },
        }
        cherrypy.config.update({
            'global': {
                'environment': 'production',
                'server.socket_host': listen_address,
                'server.socket_port': int(listen_port),
            },
        })

        cherrypy.tree.mount(api, '/', config=conf)

    @property
    def port(self):
        return cherrypy.server.bound_addr[1]

    def start(self):
        self.log.debug("ZuulWeb starting")
        self.stream_manager.start()
        self.wsplugin = WebSocketPlugin(cherrypy.engine)
        self.wsplugin.subscribe()
        cherrypy.engine.start()

    def stop(self):
        self.log.debug("ZuulWeb stopping")
        self.rpc.shutdown()
        cherrypy.engine.exit()
        # Not strictly necessary, but without this, if the server is
        # started again (e.g., in the unit tests) it will reuse the
        # same host/port settings.
        cherrypy.server.httpserver = None
        self.wsplugin.unsubscribe()
        self.stream_manager.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    import zuul.lib.connections
    connections = zuul.lib.connections.ConnectionRegistry()
    z = ZuulWeb(listen_address="127.0.0.1", listen_port=9000,
                gear_server="127.0.0.1", gear_port=4730,
                connections=connections, enable_admin_endpoints=True,
                JWTsecret='secret')
    z.start()
    cherrypy.engine.block()
