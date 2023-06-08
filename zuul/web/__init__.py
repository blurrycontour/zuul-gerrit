# Copyright (c) 2017 Red Hat
# Copyright 2021-2022 Acme Gating, LLC
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
from collections import defaultdict
from contextlib import suppress

from opentelemetry import trace
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
import codecs
import copy
from datetime import datetime
import json
import logging
import os
import time
import select
import ssl
import threading
import uuid
import prometheus_client
import urllib.parse

import zuul.executor.common
from zuul import exceptions
from zuul.configloader import ConfigLoader
from zuul.connection import BaseConnection, ReadOnlyBranchCacheError
import zuul.lib.repl
from zuul.lib import commandsocket, encryption, streamer_utils, tracing
from zuul.lib.ansible import AnsibleManager
from zuul.lib.jsonutil import ZuulJSONEncoder
from zuul.lib.keystorage import KeyStorage
from zuul.lib.monitoring import MonitoringServer
from zuul.lib.re2util import filter_allowed_disallowed
from zuul import model
from zuul.model import (
    Abide,
    BuildSet,
    Branch,
    ChangeQueue,
    DequeueEvent,
    EnqueueEvent,
    HoldRequest,
    PromoteEvent,
    QueueItem,
    SystemAttributes,
    UnparsedAbideConfig,
    WebInfo,
)
from zuul.version import get_version_string
from zuul.zk import ZooKeeperClient
from zuul.zk.components import COMPONENT_REGISTRY, WebComponent
from zuul.zk.config_cache import SystemConfigCache
from zuul.zk.event_queues import (
    TenantManagementEventQueue,
    TenantTriggerEventQueue,
    PipelineManagementEventQueue,
    PipelineResultEventQueue,
    PipelineTriggerEventQueue,
)
from zuul.zk.executor import ExecutorApi
from zuul.zk.layout import LayoutStateStore
from zuul.zk.locks import tenant_read_lock
from zuul.zk.nodepool import ZooKeeperNodepool
from zuul.zk.system import ZuulSystem
from zuul.zk.zkobject import LocalZKContext, ZKContext
from zuul.lib.auth import AuthenticatorRegistry
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.statsd import get_statsd, normalize_statsd_name
from zuul.web.logutil import ZuulCherrypyLogManager

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
cherrypy.tools.websocket = WebSocketTool()

COMMANDS = [
    commandsocket.StopCommand,
    commandsocket.ReplCommand,
    commandsocket.NoReplCommand,
]


def get_zuul_request_id():
    request = cherrypy.serving.request
    if not hasattr(request, 'zuul_request_id'):
        request.zuul_request_id = uuid.uuid4().hex
    return request.zuul_request_id


def get_request_logger(logger=None):
    if logger is None:
        logger = logging.getLogger("zuul.web")
    zuul_request_id = get_zuul_request_id()
    return get_annotated_logger(logger, None, request=zuul_request_id)


class APIError(cherrypy.HTTPError):
    def __init__(self, code, json_doc=None):
        self._json_doc = json_doc
        super().__init__(code)

    def set_response(self):
        super().set_response()
        resp = cherrypy.response
        if self._json_doc:
            ret = json.dumps(self._json_doc).encode('utf8')
            resp.body = ret
            resp.headers['Content-Type'] = 'application/json'
            resp.headers["Content-Length"] = len(ret)
        else:
            resp.body = b''
            resp.headers["Content-Length"] = '0'


class SaveParamsTool(cherrypy.Tool):
    """
    Save the URL parameters to allow them to take precedence over query
    string parameters.
    """
    def __init__(self):
        cherrypy.Tool.__init__(self, 'on_start_resource',
                               self.saveParams, priority=10)

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


def handle_options(allowed_methods=None):
    if cherrypy.request.method == 'OPTIONS':
        methods = allowed_methods or ['GET', 'OPTIONS']
        if allowed_methods and 'OPTIONS' not in allowed_methods:
            methods = methods + ['OPTIONS']
        # discard decorated handler
        request = cherrypy.serving.request
        request.handler = None
        # Set CORS response headers
        resp = cherrypy.response
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] =\
            ', '.join(['Authorization', 'Content-Type'])
        resp.headers['Access-Control-Allow-Methods'] =\
            ', '.join(methods)
        # Allow caching of the preflight response
        resp.headers['Access-Control-Max-Age'] = 86400
        resp.status = 204


cherrypy.tools.handle_options = cherrypy.Tool('on_start_resource',
                                              handle_options,
                                              priority=50)


class AuthInfo:
    def __init__(self, uid, admin):
        self.uid = uid
        self.admin = admin


def _check_auth(require_admin=False, require_auth=False, tenant=None):
    if require_admin:
        require_auth = True
    request = cherrypy.serving.request
    zuulweb = request.app.root

    if tenant:
        if not require_auth and tenant.access_rules:
            # This tenant requires auth for read-only access
            require_auth = True
    else:
        if not require_auth and zuulweb.zuulweb.abide.api_root.access_rules:
            # The API root requires auth for read-only access
            require_auth = True
    # Always set the auth variable
    request.params['auth'] = None

    basic_error = zuulweb._basic_auth_header_check(required=require_auth)
    if basic_error is not None:
        return
    claims, token_error = zuulweb._auth_token_check(required=require_auth)
    if token_error is not None:
        return
    access, admin = zuulweb._isAuthorized(tenant, claims)
    if (require_auth and not access) or (require_admin and not admin):
        raise APIError(403)

    request.params['auth'] = AuthInfo(claims['__zuul_uid_claim'],
                                      admin)


def check_root_auth(**kw):
    """Use this for root-level (non-tenant) methods"""
    cherrypy.response.headers['Access-Control-Allow-Origin'] = '*'
    request = cherrypy.serving.request
    if request.handler is None:
        # handle_options has already aborted the request.
        return
    return _check_auth(**kw)


def check_tenant_auth(**kw):
    """Use this for tenant-scoped methods"""
    cherrypy.response.headers['Access-Control-Allow-Origin'] = '*'
    request = cherrypy.serving.request
    zuulweb = request.app.root
    if request.handler is None:
        # handle_options has already aborted the request.
        return

    tenant_name = request.params.get('tenant_name')
    # Always set the tenant variable
    tenant = zuulweb._getTenantOrRaise(tenant_name)
    request.params['tenant'] = tenant
    return _check_auth(**kw, tenant=tenant)


cherrypy.tools.check_root_auth = cherrypy.Tool('on_start_resource',
                                               check_root_auth,
                                               priority=90)
cherrypy.tools.check_tenant_auth = cherrypy.Tool('on_start_resource',
                                                 check_tenant_auth,
                                                 priority=90)


class StatsTool(cherrypy.Tool):
    def __init__(self, statsd, metrics):
        self.statsd = statsd
        self.metrics = metrics
        self.hostname = normalize_statsd_name(socket.getfqdn())
        cherrypy.Tool.__init__(self, 'on_start_resource',
                               self.emitStats)

    def emitStats(self):
        idle = cherrypy.server.httpserver.requests.idle
        qsize = cherrypy.server.httpserver.requests.qsize
        self.metrics.threadpool_idle.set(idle)
        self.metrics.threadpool_queue.set(qsize)
        if self.statsd:
            self.statsd.gauge(
                f'zuul.web.server.{self.hostname}.threadpool.idle',
                idle)
            self.statsd.gauge(
                f'zuul.web.server.{self.hostname}.threadpool.queue',
                qsize)


class WebMetrics:
    def __init__(self):
        self.threadpool_idle = prometheus_client.Gauge(
            'web_threadpool_idle', 'The number of idle worker threads')
        self.threadpool_queue = prometheus_client.Gauge(
            'web_threadpool_queue', 'The number of queued requests')
        self.streamers = prometheus_client.Gauge(
            'web_streamers', 'The number of log streamers currently operating')


# Custom JSONEncoder that combines the ZuulJSONEncoder with cherrypy's
# JSON functionality.
class ZuulWebJSONEncoder(ZuulJSONEncoder):

    def iterencode(self, value):
        # Adapted from cherrypy/_json.py
        for chunk in super().iterencode(value):
            yield chunk.encode("utf-8")


json_encoder = ZuulWebJSONEncoder()


def json_handler(*args, **kwargs):
    # Adapted from cherrypy/lib/jsontools.py
    value = cherrypy.serving.request._json_inner_handler(*args, **kwargs)
    return json_encoder.iterencode(value)


class ChangeFilter(object):
    def __init__(self, desired):
        self.desired = desired

    def filterPayload(self, payload):
        status = []
        for pipeline in payload['pipelines']:
            for change_queue in pipeline.get('change_queues', []):
                for head in change_queue['heads']:
                    for change in head:
                        if self.wantChange(change):
                            status.append(copy.deepcopy(change))
        return status

    def wantChange(self, change):
        return change['id'] == self.desired


class LogStreamHandler(WebSocket):
    def __init__(self, *args, **kw):
        kw['heartbeat_freq'] = 20
        self.log = get_request_logger()
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

        try:
            port_location = streamer_utils.getJobLogStreamAddress(
                self.zuulweb.executor_api,
                request['uuid'], source_zone=self.zuulweb.zone)
        except exceptions.StreamingError as e:
            return self.logClose(4011, str(e))

        if not port_location:
            return self.logClose(4011, "Error with log streaming")

        self.streamer = LogStreamer(
            self.zuulweb, self,
            port_location['server'], port_location['port'],
            request['uuid'], port_location.get('use_ssl'))


class LogStreamer(object):
    def __init__(self, zuulweb, websocket, server, port, build_uuid, use_ssl):
        """
        Create a client to connect to the finger streamer and pull results.

        :param str server: The executor server running the job.
        :param str port: The executor server port.
        :param str build_uuid: The build UUID to stream.
        """
        self.fileno = None
        self.log = websocket.log
        self.log.debug("Connecting to finger server %s:%s", server, port)
        Decoder = codecs.getincrementaldecoder('utf8')
        self.decoder = Decoder()
        self.zuulweb = zuulweb
        self.finger_socket = socket.create_connection(
            (server, port), timeout=10)
        if use_ssl:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = self.zuulweb.finger_tls_verify_hostnames
            context.load_cert_chain(
                self.zuulweb.finger_tls_cert, self.zuulweb.finger_tls_key)
            context.load_verify_locations(self.zuulweb.finger_tls_ca)
            self.finger_socket = context.wrap_socket(
                self.finger_socket, server_hostname=server)

        self.finger_socket.settimeout(None)
        self.websocket = websocket
        self.uuid = build_uuid
        msg = "%s\n" % build_uuid    # Must have a trailing newline!
        self.finger_socket.sendall(msg.encode('utf-8'))
        self.fileno = self.finger_socket.fileno()
        self.zuulweb.stream_manager.registerStreamer(self)

    def __repr__(self):
        return '<LogStreamer %s uuid:%s fd:%s>' % (
            self.websocket, self.uuid, self.fileno)

    def errorClose(self):
        try:
            self.websocket.logClose(4011, "Unknown error")
        except Exception:
            self.log.exception("Error closing web:")

    def closeSocket(self):
        try:
            self.finger_socket.close()
        except Exception:
            self.log.exception("Error closing streamer socket:")

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
    def __init__(self, zuulweb):
        self.zuulweb = zuulweb
        self.zk_client = zuulweb.zk_client
        self.system = ZuulSystem(self.zk_client)
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client,
                                             enable_node_cache=True)
        self.status_caches = {}
        self.status_cache_times = {}
        self.status_cache_locks = defaultdict(threading.Lock)
        self.tenants_cache = []
        self.tenants_cache_time = 0
        self.tenants_cache_lock = threading.Lock()

        self.cache_expiry = 1
        self.static_cache_expiry = zuulweb.static_cache_expiry
        # SQL build query timeout, in milliseconds:
        self.query_timeout = 30000

    @property
    def log(self):
        return get_request_logger()

    def _basic_auth_header_check(self, required=True):
        """make sure protected endpoints have a Authorization header with the
        bearer token."""
        token = cherrypy.request.headers.get('Authorization', None)
        # Add basic checks here
        if token is None:
            e = 'Missing "Authorization" header'
            e_desc = e
        elif not token.lower().startswith('bearer '):
            e = 'Invalid Authorization header format'
            e_desc = '"Authorization" header must start with "Bearer"'
        else:
            return None
        error_header = '''Bearer realm="%s"
       error="%s"
       error_description="%s"''' % (self.zuulweb.authenticators.default_realm,
                                    e,
                                    e_desc)
        error_data = {'description': e_desc,
                      'error': e,
                      'realm': self.zuulweb.authenticators.default_realm}
        if required:
            cherrypy.response.headers["WWW-Authenticate"] = error_header
            raise APIError(401, error_data)
        return error_data

    def _auth_token_check(self, required=True):
        rawToken = \
            cherrypy.request.headers['Authorization'][len('Bearer '):]
        try:
            claims = self.zuulweb.authenticators.authenticate(rawToken)
        except exceptions.AuthTokenException as e:
            if required:
                for header, contents in e.getAdditionalHeaders().items():
                    cherrypy.response.headers[header] = contents
                raise APIError(e.HTTPError)
            return ({},
                    {'description': e.error_description,
                     'error': e.error,
                     'realm': e.realm})
        return (claims, None)

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options(allowed_methods=['POST', ])
    @cherrypy.tools.check_tenant_auth(require_admin=True)
    def dequeue(self, tenant_name, tenant, auth, project_name):
        if cherrypy.request.method != 'POST':
            raise cherrypy.HTTPError(405)
        self.log.info(f'User {auth.uid} requesting dequeue on '
                      f'{tenant_name}/{project_name}')

        project = self._getProjectOrRaise(tenant, project_name)

        body = cherrypy.request.json
        if 'pipeline' in body and (
                ('change' in body and 'ref' not in body) or
                ('change' not in body and 'ref' in body)):
            # Validate the pipeline so we can enqueue the event directly
            # in the pipeline management event queue and don't need to
            # take the detour via the tenant management event queue.
            pipeline_name = body['pipeline']
            pipeline = tenant.layout.pipelines.get(pipeline_name)
            if pipeline is None:
                raise cherrypy.HTTPError(400, 'Unknown pipeline')

            event = DequeueEvent(
                tenant_name, pipeline_name, project.canonical_hostname,
                project.name, body.get('change', None), body.get('ref', None))
            event.zuul_event_id = get_zuul_request_id()
            self.zuulweb.pipeline_management_events[tenant_name][
                pipeline_name].put(event)
        else:
            raise cherrypy.HTTPError(400, 'Invalid request body')
        return True

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options(allowed_methods=['POST', ])
    @cherrypy.tools.check_tenant_auth(require_admin=True)
    def enqueue(self, tenant_name, tenant, auth, project_name):
        if cherrypy.request.method != 'POST':
            raise cherrypy.HTTPError(405)
        self.log.info(f'User {auth.uid} requesting enqueue on '
                      f'{tenant_name}/{project_name}')

        project = self._getProjectOrRaise(tenant, project_name)

        body = cherrypy.request.json
        if 'pipeline' not in body:
            raise cherrypy.HTTPError(400, 'Invalid request body')

        # Validate the pipeline so we can enqueue the event directly
        # in the pipeline management event queue and don't need to
        # take the detour via the tenant management event queue.
        pipeline_name = body['pipeline']
        pipeline = tenant.layout.pipelines.get(pipeline_name)
        if pipeline is None:
            raise cherrypy.HTTPError(400, 'Unknown pipeline')

        if 'change' in body:
            return self._enqueue(tenant, project, pipeline, body['change'])
        elif all(p in body for p in ['ref', 'oldrev', 'newrev']):
            return self._enqueue_ref(tenant, project, pipeline, body['ref'],
                                     body['oldrev'], body['newrev'])
        else:
            raise cherrypy.HTTPError(400, 'Invalid request body')

    def _enqueue(self, tenant, project, pipeline, change):
        event = EnqueueEvent(tenant.name, pipeline.name,
                             project.canonical_hostname, project.name,
                             change, ref=None, oldrev=None, newrev=None)
        event.zuul_event_id = get_zuul_request_id()
        self.zuulweb.pipeline_management_events[tenant.name][
            pipeline.name].put(event)

        return True

    def _enqueue_ref(self, tenant, project, pipeline, ref, oldrev, newrev):
        event = EnqueueEvent(tenant.name, pipeline.name,
                             project.canonical_hostname, project.name,
                             change=None, ref=ref, oldrev=oldrev,
                             newrev=newrev)
        event.zuul_event_id = get_zuul_request_id()
        self.zuulweb.pipeline_management_events[tenant.name][
            pipeline.name].put(event)

        return True

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options(allowed_methods=['POST', ])
    @cherrypy.tools.check_tenant_auth(require_admin=True)
    def promote(self, tenant_name, tenant, auth):
        if cherrypy.request.method != 'POST':
            raise cherrypy.HTTPError(405)

        body = cherrypy.request.json
        pipeline_name = body.get('pipeline')
        changes = body.get('changes')

        self.log.info(f'User {auth.uid} requesting promote on '
                      f'{tenant_name}/{pipeline_name}')

        # Validate the pipeline so we can enqueue the event directly
        # in the pipeline management event queue and don't need to
        # take the detour via the tenant management event queue.
        pipeline = tenant.layout.pipelines.get(pipeline_name)
        if pipeline is None:
            raise cherrypy.HTTPError(400, 'Unknown pipeline')

        event = PromoteEvent(tenant_name, pipeline_name, changes)
        event.zuul_event_id = get_zuul_request_id()
        self.zuulweb.pipeline_management_events[tenant_name][
            pipeline_name].put(event)

        return True

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def autohold_list(self, tenant_name, tenant, auth, *args, **kwargs):
        # filter by project if passed as a query string
        project_name = cherrypy.request.params.get('project', None)
        return self._autohold_list(tenant_name, project_name)

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options(allowed_methods=['GET', 'POST'])
    @cherrypy.tools.check_tenant_auth()
    def autohold_project_get(self, tenant_name, tenant, auth, project_name):
        # Note: GET handling is redundant with autohold_list
        # and could be removed.
        return self._autohold_list(tenant_name, project_name)

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    # Options handled by _get method
    @cherrypy.tools.check_tenant_auth(require_admin=True)
    def autohold_project_post(self, tenant_name, tenant, auth, project_name):
        project = self._getProjectOrRaise(tenant, project_name)
        self.log.info(f'User {auth.uid} requesting autohold on '
                      f'{tenant_name}/{project_name}')

        jbody = cherrypy.request.json

        # Validate the payload
        jbody['change'] = jbody.get('change', None)
        jbody['ref'] = jbody.get('ref', None)
        count = jbody.get('count')
        if jbody['change'] and jbody['ref']:
            raise cherrypy.HTTPError(
                400, 'change and ref are mutually exclusive')
        if not all(p in jbody for p in [
                'job', 'count', 'change', 'ref', 'reason',
                'node_hold_expiration']):
            raise cherrypy.HTTPError(400, 'Invalid request body')
        if count < 0:
            raise cherrypy.HTTPError(400, "Count must be greater 0")

        project_name = project.canonical_name

        if jbody['change']:
            ref_filter = project.source.getRefForChange(jbody['change'])
        elif jbody['ref']:
            ref_filter = str(jbody['ref'])
        else:
            ref_filter = ".*"

        self._autohold(tenant_name, project_name, jbody['job'], ref_filter,
                       jbody['reason'], jbody['count'],
                       jbody['node_hold_expiration'])
        return True

    def _autohold(self, tenant_name, project_name, job_name, ref_filter,
                  reason, count, node_hold_expiration):
        key = (tenant_name, project_name, job_name, ref_filter)
        self.log.debug("Autohold requested for %s", key)

        request = HoldRequest()
        request.tenant = tenant_name
        request.project = project_name
        request.job = job_name
        request.ref_filter = ref_filter
        request.reason = reason
        request.max_count = count

        zuul_globals = self.zuulweb.globals
        # Set node_hold_expiration to default if no value is supplied
        if node_hold_expiration is None:
            node_hold_expiration = zuul_globals.default_hold_expiration

        # Reset node_hold_expiration to max if it exceeds the max
        elif zuul_globals.max_hold_expiration and (
                node_hold_expiration == 0 or
                node_hold_expiration > zuul_globals.max_hold_expiration):
            node_hold_expiration = zuul_globals.max_hold_expiration

        request.node_expiration = node_hold_expiration

        # No need to lock it since we are creating a new one.
        self.zk_nodepool.storeHoldRequest(request)

    def _autohold_list(self, tenant_name, project_name=None):
        result = []
        for request_id in self.zk_nodepool.getHoldRequests():
            request = self.zk_nodepool.getHoldRequest(request_id)
            if not request:
                continue

            if tenant_name != request.tenant:
                continue

            if project_name is None or request.project.endswith(project_name):
                result.append({
                    'id': request.id,
                    'tenant': request.tenant,
                    'project': request.project,
                    'job': request.job,
                    'ref_filter': request.ref_filter,
                    'max_count': request.max_count,
                    'current_count': request.current_count,
                    'reason': request.reason,
                    'node_expiration': request.node_expiration,
                    'expired': request.expired,
                    'nodes': request.nodes,
                })

        return result

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options(allowed_methods=['GET', 'DELETE', ])
    @cherrypy.tools.check_tenant_auth()
    def autohold_get(self, tenant_name, tenant, auth, request_id):
        request = self._getAutoholdRequest(tenant_name, request_id)
        return {
            'id': request.id,
            'tenant': request.tenant,
            'project': request.project,
            'job': request.job,
            'ref_filter': request.ref_filter,
            'max_count': request.max_count,
            'current_count': request.current_count,
            'reason': request.reason,
            'node_expiration': request.node_expiration,
            'expired': request.expired,
            'nodes': request.nodes,
        }

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    # Options handled by get method
    @cherrypy.tools.check_tenant_auth(require_admin=True)
    def autohold_delete(self, tenant_name, tenant, auth, request_id):
        request = self._getAutoholdRequest(tenant_name, request_id)
        self.log.info(f'User {auth.uid} requesting autohold-delete on '
                      f'{request.tenant}/{request.project}')

        # User is authorized, so remove the autohold request
        self.log.debug("Removing autohold %s", request)
        try:
            self.zk_nodepool.deleteHoldRequest(request)
        except Exception:
            self.log.exception(
                "Error removing autohold request %s:", request)

        cherrypy.response.status = 204

    def _getAutoholdRequest(self, tenant_name, request_id):
        hold_request = None
        try:
            hold_request = self.zk_nodepool.getHoldRequest(request_id)
        except Exception:
            self.log.exception("Error retrieving autohold ID %s", request_id)

        if hold_request is None:
            raise cherrypy.HTTPError(
                404, f'Hold request {request_id} not found.')

        if tenant_name != hold_request.tenant:
            # return 404 rather than 403 to avoid leaking tenant info
            raise cherrypy.HTTPError(
                404, 'Hold request {request_id} not found.')

        return hold_request

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_root_auth()
    def index(self, auth):
        return {
            'info': '/api/info',
            'connections': '/api/connections',
            'components': '/api/components',
            'authorizations': '/api/authorizations',
            'tenants': '/api/tenants',
            'tenant_info': '/api/tenant/{tenant}/info',
            'status': '/api/tenant/{tenant}/status',
            'status_change': '/api/tenant/{tenant}/status/change/{change}',
            'jobs': '/api/tenant/{tenant}/jobs',
            'job': '/api/tenant/{tenant}/job/{job_name}',
            'projects': '/api/tenant/{tenant}/projects',
            'project': '/api/tenant/{tenant}/project/{project:.*}',
            'project_freeze_jobs': '/api/tenant/{tenant}/pipeline/{pipeline}/'
                                   'project/{project:.*}/branch/{branch:.*}/'
                                   'freeze-jobs',
            'pipelines': '/api/tenant/{tenant}/pipelines',
            'semaphores': '/api/tenant/{tenant}/semaphores',
            'labels': '/api/tenant/{tenant}/labels',
            'nodes': '/api/tenant/{tenant}/nodes',
            'key': '/api/tenant/{tenant}/key/{project:.*}.pub',
            'project_ssh_key': '/api/tenant/{tenant}/project-ssh-key/'
                               '{project:.*}.pub',
            'console_stream': '/api/tenant/{tenant}/console-stream',
            'badge': '/api/tenant/{tenant}/badge',
            'builds': '/api/tenant/{tenant}/builds',
            'build': '/api/tenant/{tenant}/build/{uuid}',
            'buildsets': '/api/tenant/{tenant}/buildsets',
            'buildset': '/api/tenant/{tenant}/buildset/{uuid}',
            'config_errors': '/api/tenant/{tenant}/config-errors',
            'tenant_authorizations': ('/api/tenant/{tenant}'
                                      '/authorizations'),
            'autohold': '/api/tenant/{tenant}/project/{project:.*}/autohold',
            'autohold_list': '/api/tenant/{tenant}/autohold',
            'autohold_by_request_id': ('/api/tenant/{tenant}'
                                       '/autohold/{request_id}'),
            'autohold_delete': ('/api/tenant/{tenant}'
                                '/autohold/{request_id}'),
            'enqueue': '/api/tenant/{tenant}/project/{project:.*}/enqueue',
            'dequeue': '/api/tenant/{tenant}/project/{project:.*}/dequeue',
            'promote': '/api/tenant/{tenant}/promote',
        }

    @cherrypy.expose
    @cherrypy.tools.handle_options()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    # Info endpoints never require authentication because they supply
    # authentication information.
    def info(self):
        info = self.zuulweb.info.copy()
        auth_info = info.capabilities.capabilities['auth']

        root_realm = self.zuulweb.abide.api_root.default_auth_realm
        if root_realm:
            auth_info['default_realm'] = root_realm
        read_protected = bool(self.zuulweb.abide.api_root.access_rules)
        auth_info['read_protected'] = read_protected
        return self._handleInfo(info)

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    # Info endpoints never require authentication because they supply
    # authentication information.
    def tenant_info(self, tenant_name):
        info = self.zuulweb.info.copy()
        auth_info = info.capabilities.capabilities['auth']
        info.tenant = tenant_name
        tenant = self.zuulweb.abide.tenants.get(tenant_name)
        if tenant is not None:
            # TODO: should we return 404 if tenant not found?
            if tenant.default_auth_realm is not None:
                auth_info['default_realm'] = tenant.default_auth_realm
            read_protected = bool(tenant.access_rules)
            auth_info['read_protected'] = read_protected
        return self._handleInfo(info)

    def _handleInfo(self, info):
        ret = {'info': info.toDict()}
        resp = cherrypy.response
        if self.static_cache_expiry:
            resp.headers['Cache-Control'] = "public, max-age=%d" % \
                self.static_cache_expiry
        resp.last_modified = self.zuulweb.start_time
        # We don't wrap info methods with check_auth
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return ret

    def _isAuthorized(self, tenant, claims):
        # First, check for zuul.admin override
        if tenant:
            tenant_name = tenant.name
            admin_rules = tenant.admin_rules
            access_rules = tenant.access_rules
        else:
            tenant_name = '*'
            admin_rules = []
            access_rules = self.zuulweb.abide.api_root.access_rules
        override = claims.get('zuul', {}).get('admin', [])
        if (override == '*' or
            (isinstance(override, list) and tenant_name in override)):
            return (True, True)

        if not tenant:
            tenant_name = '<root>'

        if access_rules:
            access = False
        else:
            access = True
        for rule_name in access_rules:
            rule = self.zuulweb.abide.authz_rules.get(rule_name)
            if not rule:
                self.log.error('Undefined rule "%s"', rule_name)
                continue
            self.log.debug('Applying access rule "%s" from '
                           'tenant "%s" to claims %s',
                           rule_name, tenant_name, json.dumps(claims))
            authorized = rule(claims, tenant)
            if authorized:
                if '__zuul_uid_claim' in claims:
                    uid = claims['__zuul_uid_claim']
                else:
                    uid = json.dumps(claims)
                self.log.info('%s authorized access on '
                              'tenant "%s" by rule "%s"',
                              uid, tenant_name, rule_name)
                access = True
                break

        admin = False
        for rule_name in admin_rules:
            rule = self.zuulweb.abide.authz_rules.get(rule_name)
            if not rule:
                self.log.error('Undefined rule "%s"', rule_name)
                continue
            self.log.debug('Applying admin rule "%s" from '
                           'tenant "%s" to claims %s',
                           rule_name, tenant_name, json.dumps(claims))
            authorized = rule(claims, tenant)
            if authorized:
                if '__zuul_uid_claim' in claims:
                    uid = claims['__zuul_uid_claim']
                else:
                    uid = json.dumps(claims)
                self.log.info('%s authorized admin on '
                              'tenant "%s" by rule "%s"',
                              uid, tenant_name, rule_name)
                access = admin = True
                break
        return (access, admin)

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_root_auth(require_auth=True)
    def root_authorizations(self, auth):
        return {'zuul': {'admin': auth.admin,
                         'scope': ['*']}, }

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth(require_auth=True)
    def tenant_authorizations(self, tenant_name, tenant, auth):
        return {'zuul': {'admin': auth.admin,
                         'scope': [tenant_name, ]}, }

    def _tenants(self):
        result = []
        with self.zuulweb.zk_context as ctx:
            for tenant_name, tenant in sorted(
                    self.zuulweb.abide.tenants.items()):
                queue_size = 0
                for pipeline in tenant.layout.pipelines.values():
                    status = pipeline.summary.refresh(ctx)
                    for queue in status.get("change_queues", []):
                        for head in queue["heads"]:
                            for item in head:
                                if item["live"]:
                                    queue_size += 1

                result.append({
                    'name': tenant_name,
                    'projects': len(tenant.untrusted_projects),
                    'queue': queue_size,
                })
        return result

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_root_auth()
    def tenants(self, auth):
        cache_time = self.tenants_cache_time
        if time.time() - cache_time > self.cache_expiry:
            with self.tenants_cache_lock:
                self.tenants_cache = self._tenants()
                self.tenants_cache_time = time.time()

        resp = cherrypy.response
        resp.headers["Cache-Control"] = f"public, max-age={self.cache_expiry}"
        last_modified = datetime.utcfromtimestamp(
            self.tenants_cache_time
        )
        last_modified_header = last_modified.strftime('%a, %d %b %Y %X GMT')
        resp.headers["Last-modified"] = last_modified_header
        return self.tenants_cache

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_root_auth()
    def connections(self, auth):
        ret = [s.connection.toDict()
               for s in self.zuulweb.connections.getSources()]
        return ret

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type="application/json; charset=utf-8")
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_root_auth()
    def components(self, auth):
        ret = {}
        for kind, components in self.zuulweb.component_registry.all():
            for comp in components:
                comp_json = {
                    "hostname": comp.hostname,
                    "state": comp.state,
                    "version": comp.version,
                }
                ret.setdefault(kind, []).append(comp_json)
        return ret

    def _getStatus(self, tenant):
        cache_time = self.status_cache_times.get(tenant.name, 0)
        if tenant.name not in self.status_cache_locks or \
           (time.time() - cache_time) > self.cache_expiry:
            if self.status_cache_locks[tenant.name].acquire(
                blocking=False
            ):
                try:
                    self.status_caches[tenant.name] =\
                        self.formatStatus(tenant)
                    self.status_cache_times[tenant.name] =\
                        time.time()
                finally:
                    self.status_cache_locks[tenant.name].release()
            if not self.status_caches.get(tenant.name):
                # If the cache is empty at this point it means that we didn't
                # get the lock but another thread is initializing the cache
                # for the first time. In this case we just wait for the lock
                # to wait for it to finish.
                with self.status_cache_locks[tenant.name]:
                    pass
        payload = self.status_caches[tenant.name]
        resp = cherrypy.response
        resp.headers["Cache-Control"] = f"public, max-age={self.cache_expiry}"
        last_modified = datetime.utcfromtimestamp(
            self.status_cache_times[tenant.name]
        )
        last_modified_header = last_modified.strftime('%a, %d %b %Y %X GMT')
        resp.headers["Last-modified"] = last_modified_header
        resp.headers['Content-Type'] = 'application/json; charset=utf-8'
        return payload

    def formatStatus(self, tenant):
        data = {}
        data['zuul_version'] = self.zuulweb.component_info.version

        data['trigger_event_queue'] = {}
        data['trigger_event_queue']['length'] = len(
            self.zuulweb.trigger_events[tenant.name])
        data['management_event_queue'] = {}
        data['management_event_queue']['length'] = len(
            self.zuulweb.management_events[tenant.name]
        )
        data['connection_event_queues'] = {}
        for connection in self.zuulweb.connections.connections.values():
            queue = connection.getEventQueue()
            if queue is not None:
                data['connection_event_queues'][connection.connection_name] = {
                    'length': len(queue),
                }

        layout_state = self.zuulweb.tenant_layout_state[tenant.name]
        data['last_reconfigured'] = layout_state.last_reconfigured * 1000

        pipelines = []
        data['pipelines'] = pipelines

        trigger_event_queues = self.zuulweb.pipeline_trigger_events[
            tenant.name]
        result_event_queues = self.zuulweb.pipeline_result_events[tenant.name]
        management_event_queues = self.zuulweb.pipeline_management_events[
            tenant.name]
        with self.zuulweb.zk_context as ctx:
            for pipeline in tenant.layout.pipelines.values():
                status = pipeline.summary.refresh(ctx)
                status['trigger_events'] = len(
                    trigger_event_queues[pipeline.name])
                status['result_events'] = len(
                    result_event_queues[pipeline.name])
                status['management_events'] = len(
                    management_event_queues[pipeline.name])
                pipelines.append(status)
        return data, json.dumps(data).encode('utf-8')

    def _getTenantOrRaise(self, tenant_name):
        tenant = self.zuulweb.abide.tenants.get(tenant_name)
        if tenant:
            return tenant
        if tenant_name not in self.zuulweb.unparsed_abide.tenants:
            raise cherrypy.HTTPError(404, "Unknown tenant")
        self.log.warning("Tenant %s isn't loaded", tenant_name)
        raise cherrypy.HTTPError(204, f"Tenant {tenant_name} isn't ready")

    def _getProjectOrRaise(self, tenant, project_name):
        _, project = tenant.getProject(project_name)
        if not project:
            raise cherrypy.HTTPError(404, "Unknown project")
        return project

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def status(self, tenant_name, tenant, auth):
        return self._getStatus(tenant)[1]

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def status_change(self, tenant_name, tenant, auth, change):
        payload = self._getStatus(tenant)[0]
        result_filter = ChangeFilter(change)
        return result_filter.filterPayload(payload)

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(
        content_type='application/json; charset=utf-8', handler=json_handler,
    )
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def jobs(self, tenant_name, tenant, auth):
        result = []
        for job_name in sorted(tenant.layout.jobs):
            desc = None
            tags = set()
            variants = []
            for variant in tenant.layout.jobs[job_name]:
                if not desc and variant.description:
                    desc = variant.description.split('\n')[0]
                if variant.tags:
                    tags.update(list(variant.tags))
                job_variant = {}
                if not variant.isBase():
                    if variant.parent:
                        job_variant['parent'] = str(variant.parent)
                    else:
                        job_variant['parent'] = tenant.default_base_job
                branches = variant.getBranches()
                if branches:
                    job_variant['branches'] = branches
                if job_variant:
                    variants.append(job_variant)

            job_output = {"name": job_name}
            if desc:
                job_output["description"] = desc
            if variants:
                job_output["variants"] = variants
            if tags:
                job_output["tags"] = list(tags)
            result.append(job_output)

        return result

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def config_errors(self, tenant_name, tenant, auth):
        ret = [
            {
                'source_context': e.key.context.toDict(),
                'error': e.error,
                'short_error': e.short_error,
                'severity': e.severity,
                'name': e.name,
            }
            for e in tenant.layout.loading_errors.errors
        ]
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(
        content_type='application/json; charset=utf-8', handler=json_handler)
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def job(self, tenant_name, tenant, auth, job_name):
        job_name = urllib.parse.unquote_plus(job_name)
        job_variants = tenant.layout.jobs.get(job_name)
        result = []
        for job in job_variants:
            result.append(job.toDict(tenant))

        return result

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def projects(self, tenant_name, tenant, auth):
        result = []
        for project in tenant.config_projects:
            pobj = project.toDict()
            pobj['type'] = "config"
            result.append(pobj)
        for project in tenant.untrusted_projects:
            pobj = project.toDict()
            pobj['type'] = "untrusted"
            result.append(pobj)

        return sorted(result, key=lambda project: project["name"])

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(
        content_type='application/json; charset=utf-8', handler=json_handler)
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def project(self, tenant_name, tenant, auth, project_name):
        project = self._getProjectOrRaise(tenant, project_name)

        result = project.toDict()
        result['configs'] = []
        md = tenant.layout.getProjectMetadata(project.canonical_name).toDict()
        md['merge_mode'] = model.get_merge_mode_name(md['merge_mode'])
        result['metadata'] = md
        configs = tenant.layout.getAllProjectConfigs(project.canonical_name)
        for config_obj in configs:
            config = config_obj.toDict()
            config['pipelines'] = []
            for pipeline_name, pipeline_config in sorted(
                    config_obj.pipelines.items()):
                pipeline = pipeline_config.toDict()
                pipeline['name'] = pipeline_name
                pipeline['jobs'] = []
                for jobs in pipeline_config.job_list.jobs.values():
                    job_list = []
                    for job in jobs:
                        job_list.append(job.toDict(tenant))
                    pipeline['jobs'].append(job_list)
                config['pipelines'].append(pipeline)
            result['configs'].append(config)

        return result

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def pipelines(self, tenant_name, tenant, auth):
        ret = []
        for pipeline, pipeline_config in tenant.layout.pipelines.items():
            triggers = []
            for trigger in pipeline_config.triggers:
                if isinstance(trigger.connection, BaseConnection):
                    name = trigger.connection.connection_name
                else:
                    # Trigger not based on a connection doesn't use this attr
                    name = trigger.name
                triggers.append({
                    "name": name,
                    "driver": trigger.driver.name,
                })
            ret.append({"name": pipeline, "triggers": triggers})

        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def labels(self, tenant_name, tenant, auth):
        allowed_labels = tenant.allowed_labels or []
        disallowed_labels = tenant.disallowed_labels or []
        labels = set()
        for launcher in self.zk_nodepool.getRegisteredLaunchers():
            labels.update(filter_allowed_disallowed(
                launcher.supported_labels,
                allowed_labels, disallowed_labels))
        ret = [{'name': label} for label in sorted(labels)]
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def nodes(self, tenant_name, tenant, auth):
        ret = []
        for node_id in self.zk_nodepool.getNodes(cached=True):
            node = self.zk_nodepool.getNode(node_id)
            # This returns all nodes; some of which may not be
            # intended for use by Zuul, so be extra careful checking
            # user_data.
            if not (node.user_data and
                    isinstance(node.user_data, dict) and
                    node.user_data.get('zuul_system') ==
                    self.system.system_id and
                    node.tenant_name == tenant_name):
                continue
            node_data = {}
            for key in ("id", "type", "connection_type", "external_id",
                        "provider", "state", "state_time", "comment"):
                node_data[key] = getattr(node, key, None)
            ret.append(node_data)
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def key(self, tenant_name, tenant, auth, project_name):
        project = self._getProjectOrRaise(tenant, project_name)

        key = encryption.serialize_rsa_public_key(project.public_secrets_key)
        resp = cherrypy.response
        resp.headers['Content-Type'] = 'text/plain'
        return key

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def project_ssh_key(self, tenant_name, tenant, auth, project_name):
        project = self._getProjectOrRaise(tenant, project_name)

        key = f"{project.public_ssh_key}\n"
        resp = cherrypy.response
        resp.headers['Content-Type'] = 'text/plain'
        return key

    def _datetimeToString(self, my_datetime):
        if my_datetime:
            return my_datetime.strftime('%Y-%m-%dT%H:%M:%S')
        return None

    def buildToDict(self, build, buildset=None):
        start_time = self._datetimeToString(build.start_time)
        end_time = self._datetimeToString(build.end_time)
        if build.start_time and build.end_time:
            duration = (build.end_time -
                        build.start_time).total_seconds()
        else:
            duration = None

        ret = {
            '_id': build.id,
            'uuid': build.uuid,
            'job_name': build.job_name,
            'result': build.result,
            'held': build.held,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'voting': build.voting,
            'log_url': build.log_url,
            'nodeset': build.nodeset,
            'error_detail': build.error_detail,
            'final': build.final,
            'artifacts': [],
            'provides': [],
        }

        if buildset:
            event_timestamp = self._datetimeToString(buildset.event_timestamp)
            ret.update({
                'project': buildset.project,
                'branch': buildset.branch,
                'pipeline': buildset.pipeline,
                'change': buildset.change,
                'patchset': buildset.patchset,
                'ref': buildset.ref,
                'newrev': buildset.newrev,
                'ref_url': buildset.ref_url,
                'event_id': buildset.event_id,
                'event_timestamp': event_timestamp,
                'buildset': {
                    'uuid': buildset.uuid,
                },
            })

        for artifact in build.artifacts:
            art = {
                'name': artifact.name,
                'url': artifact.url,
            }
            if artifact.meta:
                art['metadata'] = json.loads(artifact.meta)
            ret['artifacts'].append(art)
        for provides in build.provides:
            ret['provides'].append({
                'name': provides.name,
            })
        return ret

    def _get_connection(self):
        return self.zuulweb.connections.connections['database']

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def builds(self, tenant_name, tenant, auth, project=None,
               pipeline=None, change=None, branch=None, patchset=None,
               ref=None, newrev=None, uuid=None, job_name=None,
               voting=None, nodeset=None, result=None, final=None,
               held=None, complete=None, limit=50, skip=0,
               idx_min=None, idx_max=None, exclude_result=None):
        connection = self._get_connection()

        if tenant_name not in self.zuulweb.abide.tenants.keys():
            raise cherrypy.HTTPError(
                404,
                f'Tenant {tenant_name} does not exist.')

        # If final is None, we return all builds, both final and non-final
        if final is not None:
            final = final.lower() == "true"

        if complete is not None:
            complete = complete.lower() == 'true'

        try:
            _idx_max = idx_max is not None and int(idx_max) or idx_max
            _idx_min = idx_min is not None and int(idx_min) or idx_min
        except ValueError:
            raise cherrypy.HTTPError(400, 'idx_min, idx_max must be integers')

        builds = connection.getBuilds(
            tenant=tenant_name, project=project, pipeline=pipeline,
            change=change, branch=branch, patchset=patchset, ref=ref,
            newrev=newrev, uuid=uuid, job_name=job_name, voting=voting,
            nodeset=nodeset, result=result, final=final, held=held,
            complete=complete, limit=limit, offset=skip, idx_min=_idx_min,
            idx_max=_idx_max, exclude_result=exclude_result,
            query_timeout=self.query_timeout)

        return [self.buildToDict(b, b.buildset) for b in builds]

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def build(self, tenant_name, tenant, auth, uuid):
        connection = self._get_connection()

        data = connection.getBuilds(tenant=tenant_name, uuid=uuid, limit=1)
        if not data:
            raise cherrypy.HTTPError(404, "Build not found")
        data = self.buildToDict(data[0], data[0].buildset)
        return data

    def buildsetToDict(self, buildset, builds=[]):
        event_timestamp = self._datetimeToString(buildset.event_timestamp)
        start = self._datetimeToString(buildset.first_build_start_time)
        end = self._datetimeToString(buildset.last_build_end_time)
        ret = {
            '_id': buildset.id,
            'uuid': buildset.uuid,
            'result': buildset.result,
            'message': buildset.message,
            'project': buildset.project,
            'branch': buildset.branch,
            'pipeline': buildset.pipeline,
            'change': buildset.change,
            'patchset': buildset.patchset,
            'ref': buildset.ref,
            'newrev': buildset.newrev,
            'ref_url': buildset.ref_url,
            'event_id': buildset.event_id,
            'event_timestamp': event_timestamp,
            'first_build_start_time': start,
            'last_build_end_time': end,
        }
        if builds:
            ret['builds'] = []
        for build in builds:
            ret['builds'].append(self.buildToDict(build))
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def badge(self, tenant_name, tenant, auth, project=None,
              pipeline=None, branch=None):
        connection = self._get_connection()

        buildsets = connection.getBuildsets(
            tenant=tenant_name, project=project, pipeline=pipeline,
            branch=branch, complete=True, limit=1,
            query_timeout=self.query_timeout)
        if not buildsets:
            raise cherrypy.HTTPError(404, 'No buildset found')

        if buildsets[0].result == 'SUCCESS':
            file = 'passing.svg'
        else:
            file = 'failing.svg'
        path = os.path.join(self.zuulweb.static_path, file)

        # Ensure the badge are not cached
        cherrypy.response.headers['Cache-Control'] = "no-cache"

        return cherrypy.lib.static.serve_file(
            path=path, content_type="image/svg+xml")

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def buildsets(self, tenant_name, tenant, auth, project=None,
                  pipeline=None, change=None, branch=None,
                  patchset=None, ref=None, newrev=None, uuid=None,
                  result=None, complete=None, limit=50, skip=0,
                  idx_min=None, idx_max=None):
        connection = self._get_connection()

        if complete:
            complete = complete.lower() == 'true'

        try:
            _idx_max = idx_max is not None and int(idx_max) or idx_max
            _idx_min = idx_min is not None and int(idx_min) or idx_min
        except ValueError:
            raise cherrypy.HTTPError(400, 'idx_min, idx_max must be integers')

        buildsets = connection.getBuildsets(
            tenant=tenant_name, project=project, pipeline=pipeline,
            change=change, branch=branch, patchset=patchset, ref=ref,
            newrev=newrev, uuid=uuid, result=result, complete=complete,
            limit=limit, offset=skip, idx_min=_idx_min, idx_max=_idx_max,
            query_timeout=self.query_timeout)

        return [self.buildsetToDict(b) for b in buildsets]

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def buildset(self, tenant_name, tenant, auth, uuid):
        connection = self._get_connection()

        data = connection.getBuildset(tenant_name, uuid)
        if not data:
            raise cherrypy.HTTPError(404, "Buildset not found")
        data = self.buildsetToDict(data, data.builds)
        return data

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(
        content_type='application/json; charset=utf-8', handler=json_handler,
    )
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def semaphores(self, tenant_name, tenant, auth):
        result = []
        names = set(tenant.layout.semaphores.keys())
        names = names.union(tenant.global_semaphores)
        for semaphore_name in sorted(names):
            semaphore = tenant.layout.getSemaphore(
                self.zuulweb.abide, semaphore_name)
            holders = tenant.semaphore_handler.semaphoreHolders(semaphore_name)
            this_tenant = []
            other_tenants = 0
            for holder in holders:
                (holder_tenant, holder_pipeline,
                 holder_item_uuid, holder_buildset_uuid
                 ) = BuildSet.parsePath(holder['buildset_path'])
                if holder_tenant != tenant_name:
                    other_tenants += 1
                    continue
                this_tenant.append({'buildset_uuid': holder_buildset_uuid,
                                    'job_name': holder['job_name']})
            sem_out = {'name': semaphore.name,
                       'global': semaphore.global_scope,
                       'max': semaphore.max,
                       'holders': {
                           'count': len(this_tenant) + other_tenants,
                           'this_tenant': this_tenant,
                           'other_tenants': other_tenants},
                       }
            result.append(sem_out)
        return result

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.handle_options()
    # We don't check auth here since we would never fall through to it
    def console_stream_options(self, tenant_name):
        cherrypy.request.ws_handler.zuulweb = self.zuulweb

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.websocket(handler_cls=LogStreamHandler)
    # Options handling in _options method
    @cherrypy.tools.check_tenant_auth()
    def console_stream_get(self, tenant_name, tenant, auth):
        cherrypy.request.ws_handler.zuulweb = self.zuulweb

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def project_freeze_jobs(self, tenant_name, tenant, auth,
                            pipeline_name, project_name, branch_name):
        item = self._freeze_jobs(
            tenant, pipeline_name, project_name, branch_name)

        output = []
        for job in item.current_build_set.job_graph.getJobs():
            output.append({
                'name': job.name,
                'dependencies':
                    list(map(lambda x: x.toDict(), job.dependencies)),
            })

        ret = output
        return ret

    @cherrypy.expose
    @cherrypy.tools.save_params()
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @cherrypy.tools.handle_options()
    @cherrypy.tools.check_tenant_auth()
    def project_freeze_job(self, tenant_name, tenant, auth,
                           pipeline_name, project_name, branch_name,
                           job_name):
        # TODO(jhesketh): Allow a canonical change/item to be passed in which
        # would return the job with any in-change modifications.
        item = self._freeze_jobs(
            tenant, pipeline_name, project_name, branch_name)
        job = item.current_build_set.jobs.get(job_name)
        if not job:
            raise cherrypy.HTTPError(404)

        uuid = "0" * 32
        params = zuul.executor.common.construct_build_params(
            uuid, self.zuulweb.connections, job, item, item.pipeline)
        params['zuul'].update(zuul.executor.common.zuul_params_from_job(job))
        del params['job_ref']
        params['job'] = job.name
        params['zuul']['buildset'] = None
        params['timeout'] = job.timeout
        params['post_timeout'] = job.post_timeout
        params['override_branch'] = job.override_branch
        params['override_checkout'] = job.override_checkout
        params['ansible_version'] = job.ansible_version
        params['workspace_scheme'] = job.workspace_scheme
        if job.name != 'noop':
            params['playbooks'] = job.run
            params['pre_playbooks'] = job.pre_run
            params['post_playbooks'] = job.post_run
            params['cleanup_playbooks'] = job.cleanup_run
        params["nodeset"] = job.nodeset.toDict()
        params['vars'] = job.combined_variables
        params['extra_vars'] = job.extra_variables
        params['host_vars'] = job.host_variables
        params['group_vars'] = job.group_variables
        params['secret_vars'] = job.secret_parent_data

        ret = params
        return ret

    def _freeze_jobs(self, tenant, pipeline_name, project_name,
                     branch_name):

        project = self._getProjectOrRaise(tenant, project_name)
        pipeline = tenant.layout.pipelines.get(pipeline_name)
        if not pipeline:
            raise cherrypy.HTTPError(404, 'Unknown pipeline')

        change = Branch(project)
        change.branch = branch_name or "master"
        with LocalZKContext(self.log) as context:
            queue = ChangeQueue.new(context, pipeline=pipeline)
            item = QueueItem.new(context, queue=queue, change=change)
            item.freezeJobGraph(tenant.layout, context,
                                skip_file_matcher=True,
                                redact_secrets_and_keys=True)

        return item


class StaticHandler(object):
    def __init__(self, root):
        self.root = root

    def default(self, path, **kwargs):
        # Try to handle static file first
        handled = cherrypy.lib.static.staticdir(
            section="",
            dir=self.root,
            index='index.html')
        if not path or not handled:
            # When not found, serve the index.html
            return cherrypy.lib.static.serve_file(
                path=os.path.join(self.root, "index.html"),
                content_type="text/html")
        else:
            return cherrypy.lib.static.serve_file(
                path=os.path.join(self.root, path))


class StreamManager(object):
    log = logging.getLogger("zuul.web")

    def __init__(self, statsd, metrics):
        self.thread = None
        self.statsd = statsd
        self.metrics = metrics
        self.hostname = normalize_statsd_name(socket.getfqdn())
        self.streamers = {}
        self.poll = select.poll()
        self.bitmask = (select.POLLIN | select.POLLERR |
                        select.POLLHUP | select.POLLNVAL)
        self.wake_read, self.wake_write = os.pipe()
        self.poll.register(self.wake_read, self.bitmask)
        self.poll_lock = threading.Lock()

    def start(self):
        self._stopped = False
        self.thread = threading.Thread(
            target=self.run,
            name='StreamManager')
        self.thread.start()

    def stop(self):
        if self.thread:
            self._stopped = True
            os.write(self.wake_write, b'\n')
            self.thread.join()

    def run(self):
        while not self._stopped:
            try:
                self._run()
            except Exception:
                self.log.exception("Error in StreamManager run method")

    def _run(self):
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
                with self.poll_lock:
                    # Double check this now that we have the lock
                    streamer = self.streamers.get(fd)
                    if not streamer:
                        self.log.error(
                            "Unregistering missing streamer fd: %s", fd)
                        try:
                            self.poll.unregister(fd)
                        except KeyError:
                            pass

    def emitStats(self):
        streamers = len(self.streamers)
        self.metrics.streamers.set(streamers)
        if self.statsd:
            self.statsd.gauge(f'zuul.web.server.{self.hostname}.streamers',
                              streamers)

    def registerStreamer(self, streamer):
        with self.poll_lock:
            self.log.debug("Registering streamer %s", streamer)
            self.streamers[streamer.fileno] = streamer
            self.poll.register(streamer.fileno, self.bitmask)
            os.write(self.wake_write, b'\n')
        self.emitStats()

    def unregisterStreamer(self, streamer):
        with self.poll_lock:
            self.log.debug("Unregistering streamer %s", streamer)
            old_streamer = self.streamers.get(streamer.fileno)
            if old_streamer and old_streamer is streamer:
                # Otherwise, we may have a new streamer which reused
                # the fileno, so leave the poll registration in place.
                del self.streamers[streamer.fileno]
                try:
                    self.poll.unregister(streamer.fileno)
                except KeyError:
                    pass
                except Exception:
                    self.log.exception("Error unregistering streamer:")
            streamer.closeSocket()
        self.emitStats()


class ZuulWeb(object):
    log = logging.getLogger("zuul.web")
    tracer = trace.get_tracer("zuul")

    def __init__(self,
                 config,
                 connections,
                 authenticators: AuthenticatorRegistry,
                 info: WebInfo = None):
        self._running = False
        self.start_time = time.time()
        self.config = config
        self.tracing = tracing.Tracing(self.config)
        self.metrics = WebMetrics()
        self.statsd = get_statsd(config)
        self.wsplugin = None

        self.listen_address = get_default(self.config,
                                          'web', 'listen_address',
                                          '127.0.0.1')
        self.listen_port = get_default(self.config, 'web', 'port', 9000)
        self.server = None
        self.static_cache_expiry = get_default(self.config, 'web',
                                               'static_cache_expiry',
                                               3600)
        self.info = info
        self.static_path = os.path.abspath(
            get_default(self.config, 'web', 'static_path', STATIC_DIR)
        )
        self.hostname = socket.getfqdn()

        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        self.executor_api = ExecutorApi(self.zk_client, use_cache=False)

        self.component_info = WebComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()

        self.monitoring_server = MonitoringServer(self.config, 'web',
                                                  self.component_info)
        self.monitoring_server.start()

        self.component_registry = COMPONENT_REGISTRY.create(self.zk_client)

        self.system_config_thread = None
        self.system_config_cache_wake_event = threading.Event()
        self.system_config_cache = SystemConfigCache(
            self.zk_client,
            self.system_config_cache_wake_event.set)

        self.keystore = KeyStorage(
            self.zk_client, password=self._get_key_store_password())
        self.globals = SystemAttributes.fromConfig(self.config)
        self.ansible_manager = AnsibleManager(
            default_version=self.globals.default_ansible_version)
        self.abide = Abide()
        self.unparsed_abide = UnparsedAbideConfig()
        self.tenant_layout_state = LayoutStateStore(
            self.zk_client, self.system_config_cache_wake_event.set)
        self.local_layout_state = {}

        self.connections = connections
        self.authenticators = authenticators
        self.stream_manager = StreamManager(self.statsd, self.metrics)
        self.zone = get_default(self.config, 'web', 'zone')

        self.management_events = TenantManagementEventQueue.createRegistry(
            self.zk_client)
        self.pipeline_management_events = (
            PipelineManagementEventQueue.createRegistry(self.zk_client)
        )
        self.trigger_events = TenantTriggerEventQueue.createRegistry(
            self.zk_client, self.connections
        )
        self.pipeline_trigger_events = (
            PipelineTriggerEventQueue.createRegistry(
                self.zk_client, self.connections
            )
        )
        self.pipeline_result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        self.zk_context = ZKContext(self.zk_client, None, None, self.log)

        command_socket = get_default(
            self.config, 'web', 'command_socket',
            '/var/lib/zuul/web.socket'
        )

        self.command_socket = commandsocket.CommandSocket(command_socket)

        self.repl = None

        self.command_map = {
            commandsocket.StopCommand.name: self.stop,
            commandsocket.ReplCommand.name: self.startRepl,
            commandsocket.NoReplCommand.name: self.stopRepl,
        }

        self.finger_tls_key = get_default(
            self.config, 'fingergw', 'tls_key')
        self.finger_tls_cert = get_default(
            self.config, 'fingergw', 'tls_cert')
        self.finger_tls_ca = get_default(
            self.config, 'fingergw', 'tls_ca')
        self.finger_tls_verify_hostnames = get_default(
            self.config, 'fingergw', 'tls_verify_hostnames', default=True)

        route_map = cherrypy.dispatch.RoutesDispatcher()
        api = ZuulWebAPI(self)
        self.api = api
        route_map.connect('api', '/api',
                          controller=api, action='index')
        route_map.connect('api', '/api/info',
                          controller=api, action='info')
        route_map.connect('api', '/api/connections',
                          controller=api, action='connections')
        route_map.connect('api', '/api/components',
                          controller=api, action='components')
        route_map.connect('api', '/api/tenants',
                          controller=api, action='tenants')
        route_map.connect('api', '/api/tenant/{tenant_name}/info',
                          controller=api, action='tenant_info')
        route_map.connect('api', '/api/tenant/{tenant_name}/status',
                          controller=api, action='status')
        route_map.connect('api', '/api/tenant/{tenant_name}/status/change'
                          '/{change}',
                          controller=api, action='status_change')
        route_map.connect('api', '/api/tenant/{tenant_name}/semaphores',
                          controller=api, action='semaphores')
        route_map.connect('api', '/api/tenant/{tenant_name}/jobs',
                          controller=api, action='jobs')
        route_map.connect('api', '/api/tenant/{tenant_name}/job/{job_name}',
                          controller=api, action='job')
        # if no auth configured, deactivate admin routes
        if self.authenticators.authenticators:
            # route order is important, put project actions before the more
            # generic tenant/{tenant_name}/project/{project} route
            route_map.connect('api',
                              '/api/tenant/{tenant_name}/authorizations',
                              controller=api,
                              action='tenant_authorizations')
            route_map.connect('api',
                              '/api/authorizations',
                              controller=api,
                              action='root_authorizations')
            route_map.connect('api', '/api/tenant/{tenant_name}/promote',
                              controller=api, action='promote')
            route_map.connect(
                'api',
                '/api/tenant/{tenant_name}/project/{project_name:.*}/autohold',
                controller=api,
                conditions=dict(method=['GET', 'OPTIONS']),
                action='autohold_project_get')
            route_map.connect(
                'api',
                '/api/tenant/{tenant_name}/project/{project_name:.*}/autohold',
                controller=api,
                conditions=dict(method=['POST']),
                action='autohold_project_post')
            route_map.connect(
                'api',
                '/api/tenant/{tenant_name}/project/{project_name:.*}/enqueue',
                controller=api, action='enqueue')
            route_map.connect(
                'api',
                '/api/tenant/{tenant_name}/project/{project_name:.*}/dequeue',
                controller=api, action='dequeue')
        route_map.connect('api',
                          '/api/tenant/{tenant_name}/autohold/{request_id}',
                          controller=api,
                          conditions=dict(method=['GET', 'OPTIONS']),
                          action='autohold_get')
        route_map.connect('api',
                          '/api/tenant/{tenant_name}/autohold/{request_id}',
                          controller=api,
                          conditions=dict(method=['DELETE']),
                          action='autohold_delete')
        route_map.connect('api', '/api/tenant/{tenant_name}/autohold',
                          controller=api, action='autohold_list')
        route_map.connect('api', '/api/tenant/{tenant_name}/projects',
                          controller=api, action='projects')
        route_map.connect('api', '/api/tenant/{tenant_name}/project/'
                          '{project_name:.*}',
                          controller=api, action='project')
        route_map.connect(
            'api',
            '/api/tenant/{tenant_name}/pipeline/{pipeline_name}'
            '/project/{project_name:.*}/branch/{branch_name:.*}/freeze-jobs',
            controller=api, action='project_freeze_jobs'
        )
        route_map.connect(
            'api',
            '/api/tenant/{tenant_name}/pipeline/{pipeline_name}'
            '/project/{project_name:.*}/branch/{branch_name:.*}'
            '/freeze-job/{job_name}',
            controller=api, action='project_freeze_job'
        )
        route_map.connect('api', '/api/tenant/{tenant_name}/pipelines',
                          controller=api, action='pipelines')
        route_map.connect('api', '/api/tenant/{tenant_name}/labels',
                          controller=api, action='labels')
        route_map.connect('api', '/api/tenant/{tenant_name}/nodes',
                          controller=api, action='nodes')
        route_map.connect('api', '/api/tenant/{tenant_name}/key/'
                          '{project_name:.*}.pub',
                          controller=api, action='key')
        route_map.connect('api', '/api/tenant/{tenant_name}/'
                          'project-ssh-key/{project_name:.*}.pub',
                          controller=api, action='project_ssh_key')
        route_map.connect('api', '/api/tenant/{tenant_name}/console-stream',
                          controller=api, action='console_stream_get',
                          conditions=dict(method=['GET']))
        route_map.connect('api', '/api/tenant/{tenant_name}/console-stream',
                          controller=api, action='console_stream_options',
                          conditions=dict(method=['OPTIONS']))
        route_map.connect('api', '/api/tenant/{tenant_name}/builds',
                          controller=api, action='builds')
        route_map.connect('api', '/api/tenant/{tenant_name}/badge',
                          controller=api, action='badge')
        route_map.connect('api', '/api/tenant/{tenant_name}/build/{uuid}',
                          controller=api, action='build')
        route_map.connect('api', '/api/tenant/{tenant_name}/buildsets',
                          controller=api, action='buildsets')
        route_map.connect('api', '/api/tenant/{tenant_name}/buildset/{uuid}',
                          controller=api, action='buildset')
        route_map.connect('api', '/api/tenant/{tenant_name}/config-errors',
                          controller=api, action='config_errors')

        for connection in connections.connections.values():
            controller = connection.getWebController(self)
            if controller:
                cherrypy.tree.mount(
                    controller,
                    '/api/connection/%s' % connection.connection_name)

        # Add fallthrough routes at the end for the static html/js files
        route_map.connect(
            'root_static', '/{path:.*}',
            controller=StaticHandler(self.static_path),
            action='default')

        cherrypy.tools.stats = StatsTool(self.statsd, self.metrics)

        conf = {
            '/': {
                'request.dispatch': route_map,
                'tools.stats.on': True,
            }
        }
        cherrypy.config.update({
            'global': {
                'environment': 'production',
                'server.socket_host': self.listen_address,
                'server.socket_port': int(self.listen_port),
            },
        })

        app = cherrypy.tree.mount(api, '/', config=conf)
        app.log = ZuulCherrypyLogManager(appid=app.log.appid)

    @property
    def port(self):
        return cherrypy.server.bound_addr[1]

    def start(self):
        self.log.info("ZuulWeb starting")

        self._running = True
        self.component_info.state = self.component_info.INITIALIZING

        self.log.info("Starting command processor")
        self._command_running = True
        self.command_socket.start()
        self.command_thread = threading.Thread(target=self.runCommand,
                                               name='command')
        self.command_thread.daemon = True
        self.command_thread.start()

        # Wait for system config and layouts to be loaded
        self.log.info("Waiting for system config from scheduler")
        while not self.system_config_cache.is_valid:
            self.system_config_cache_wake_event.wait(1)
            if not self._running:
                return

        # Initialize the system config
        self.updateSystemConfig()

        # Wait until all layouts/tenants are loaded
        self.log.info("Waiting for all tenants to load")
        while True:
            self.system_config_cache_wake_event.clear()
            self.updateLayout()
            if (set(self.unparsed_abide.tenants.keys())
                != set(self.abide.tenants.keys())):
                while True:
                    self.system_config_cache_wake_event.wait(1)
                    if not self._running:
                        return
                    if self.system_config_cache_wake_event.is_set():
                        break
            else:
                break

        self.log.info("Starting HTTP listeners")
        self.stream_manager.start()
        self.wsplugin = WebSocketPlugin(cherrypy.engine)
        self.wsplugin.subscribe()
        cherrypy.engine.start()

        self.component_info.state = self.component_info.RUNNING

        self.system_config_thread = threading.Thread(
            target=self.updateConfig,
            name='system_config')
        self._system_config_running = True
        self.system_config_thread.daemon = True
        self.system_config_thread.start()

    def stop(self):
        self.log.info("ZuulWeb stopping")
        self._running = False
        self.component_info.state = self.component_info.STOPPED
        cherrypy.engine.exit()
        # Not strictly necessary, but without this, if the server is
        # started again (e.g., in the unit tests) it will reuse the
        # same host/port settings.
        cherrypy.server.httpserver = None
        if self.wsplugin:
            self.wsplugin.unsubscribe()
        self.stream_manager.stop()
        self._system_config_running = False
        self.system_config_cache_wake_event.set()
        if self.system_config_thread:
            self.system_config_thread.join()
        self.stopRepl()
        self._command_running = False
        self.command_socket.stop()
        self.monitoring_server.stop()
        self.tracing.stop()
        self.zk_client.disconnect()

    def join(self):
        self.command_thread.join()
        self.monitoring_server.join()

    def runCommand(self):
        while self._command_running:
            try:
                command, args = self.command_socket.get()
                if command != '_stop':
                    self.command_map[command]()
            except Exception:
                self.log.exception("Exception while processing command")

    def startRepl(self):
        if self.repl:
            return
        self.repl = zuul.lib.repl.REPLServer(self)
        self.repl.start()

    def stopRepl(self):
        if not self.repl:
            return
        self.repl.stop()
        self.repl = None

    def _get_key_store_password(self):
        try:
            return self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")

    def updateConfig(self):
        while self._system_config_running:
            try:
                self.system_config_cache_wake_event.wait()
                self.system_config_cache_wake_event.clear()
                if not self._system_config_running:
                    return
                self.updateSystemConfig()
                if not self.updateLayout():
                    # Branch cache errors with at least one tenant,
                    # try again.
                    time.sleep(10)
                    self.system_config_cache_wake_event.set()
            except Exception:
                self.log.exception("Exception while updating system config")

    def updateSystemConfig(self):
        self.log.debug("Updating system config")
        self.unparsed_abide, self.globals = self.system_config_cache.get()
        self.ansible_manager = AnsibleManager(
            default_version=self.globals.default_ansible_version)

        loader = ConfigLoader(
            self.connections, self.zk_client, self.globals,
            keystorage=self.keystore)

        tenant_names = set(self.abide.tenants)
        deleted_tenants = tenant_names.difference(
            self.unparsed_abide.tenants.keys())

        # Remove TPCs of deleted tenants
        for tenant_name in deleted_tenants:
            self.abide.clearTPCs(tenant_name)

        loader.loadAuthzRules(self.abide, self.unparsed_abide)
        loader.loadSemaphores(self.abide, self.unparsed_abide)
        loader.loadTPCs(self.abide, self.unparsed_abide)

    def updateLayout(self):
        self.log.debug("Updating layout state")
        loader = ConfigLoader(
            self.connections, self.zk_client, self.globals,
            keystorage=self.keystore)

        # We need to handle new and deleted tenants, so we need to process all
        # tenants currently known and the new ones.
        tenant_names = set(self.abide.tenants)
        tenant_names.update(self.unparsed_abide.tenants.keys())

        success = True
        for tenant_name in tenant_names:
            # Reload the tenant if the layout changed.
            try:
                self._updateTenantLayout(loader, tenant_name)
            except ReadOnlyBranchCacheError:
                self.log.info(
                    "Unable to update layout due to incomplete branch "
                    "cache, possibly due to in-progress tenant "
                    "reconfiguration; will retry")
                success = False
        self.log.debug("Done updating layout state")
        return success

    def _updateTenantLayout(self, loader, tenant_name):
        # Reload the tenant if the layout changed.
        if (self.local_layout_state.get(tenant_name)
                == self.tenant_layout_state.get(tenant_name)):
            return
        self.log.debug("Reloading tenant %s", tenant_name)
        with tenant_read_lock(self.zk_client, tenant_name):
            layout_state = self.tenant_layout_state.get(tenant_name)
            layout_uuid = layout_state and layout_state.uuid

            if layout_state:
                min_ltimes = self.tenant_layout_state.getMinLtimes(
                    layout_state)
                branch_cache_min_ltimes = (
                    layout_state.branch_cache_min_ltimes)
            else:
                # Consider all project branch caches valid if
                # we don't have a layout state.
                min_ltimes = defaultdict(
                    lambda: defaultdict(lambda: -1))
                branch_cache_min_ltimes = defaultdict(lambda: -1)

            # The tenant will be stored in self.abide.tenants after
            # it was loaded.
            tenant = loader.loadTenant(
                self.abide, tenant_name, self.ansible_manager,
                self.unparsed_abide, min_ltimes=min_ltimes,
                layout_uuid=layout_uuid,
                branch_cache_min_ltimes=branch_cache_min_ltimes)
            if tenant is not None:
                self.local_layout_state[tenant_name] = layout_state
            else:
                with suppress(KeyError):
                    del self.local_layout_state[tenant_name]
