# Copyright 2019 Red Hat, Inc.
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
import hmac
import hashlib
import json
import queue
import cherrypy
import voluptuous as v

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController


def _sign_request(body, secret):
    signature = hmac.new(
        secret.encode('utf-8'), body, hashlib.sha1).hexdigest()
    return signature, body


class GitlabConnection(BaseConnection):
    driver_name = 'gitlab'
    log = logging.getLogger("zuul.GitlabConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(GitlabConnection, self).__init__(
            driver, connection_name, connection_config)
        self.projects = {}
        self.server = self.connection_config.get('server', 'gitlab.com')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.sched = None
        self.event_queue = queue.Queue()

    def onLoad(self):
        pass

    def onStop(self):
        pass

    def getChange(self, event):
        return None

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project


class GitlabWebController(BaseWebController):

    log = logging.getLogger("zuul.GitlabWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-pagure-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'x-pagure-signature header missing.')

        project = headers['x-pagure-project']
        token = self.connection.webhook_token
        if not token:
            raise cherrypy.HTTPError(
                401, 'no webhook token for %s.' % project)

        signature, payload = _sign_request(body, token)

        if not hmac.compare_digest(str(signature), str(request_signature)):
            self.log.debug(
                "Missmatch (Payload Signature: %s, Request Signature: %s)" % (
                    signature, request_signature))
            raise cherrypy.HTTPError(
                401,
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

        return payload

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        payload = self._validate_signature(body, headers)
        json_payload = json.loads(payload.decode('utf-8'))

        job = self.zuul_web.rpc.submitJob(
            'pagure:%s:payload' % self.connection.connection_name,
            {'payload': json_payload})

        return json.loads(job.data[0])


def getSchema():
    return v.Any(str, v.Schema(dict))
