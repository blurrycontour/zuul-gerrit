# Copyright 2015 Hewlett-Packard Development Company, L.P.
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
import threading
import hmac
import hashlib
import pprint

from paste import httpserver
import webob
import webob.dec
import voluptuous as v
import github3

from zuul.connection import BaseConnection
from zuul.model import TriggerEvent

log = logging.getLogger("connection.github")


class GithubWebhookListener(threading.Thread):

    log = logging.getLogger("zuul.GithubWebhookListener")

    def __init__(self, connection):
        super(GithubWebhookListener,
              self).__init__(name="GithubWebhookListener")
        self.connection = connection
        self.port = self.connection.connection_config.get('webhook_port', '9000')
        self.server = httpserver.serve(self._app, host='0.0.0.0',
                                       port=self.port, start_loop=False)

    def run(self):
        self.server.serve_forever()

    @webob.dec.wsgify
    def _app(self, request):
        if request.path != '/payload':
            self.log.debug("HTTP Not Found: {0}".format(request.path))
            raise webob.exc.HTTPNotFound()

        if request.method != 'POST':
            self.log.debug("Only POST method is allowed.")
            raise webob.exc.HTTPInvalidMethod('Only POST method is allowed.')

        self.log.debug("Github Webhook Received.")

        self._validate_signature(request)

        self.__dispatch_event(request)

    def __dispatch_event(self, request):
        try:
            event = request.headers.get('X-Github-Event')
            self.log.debug("X-Github-Event: " + event)
        except KeyError:
            self.log.debug("Request headers missing the X-Github-Event.")
            raise webob.exc.HTTPBadRequest('Please specify a X-Github-Event '
                                           'header.')

        try:
            method = getattr(self, '_event_' + event)
        except AttributeError:
            message = "Unhandled X-Github-Event: {0}".format(event)
            self.log.debug(message)
            raise webob.exc.HTTPBadRequest(message)

        event = method(request)

        if event:
            self.log.debug('Scheduling github event: {0}'.format(event.type))
            self.connection.sched.addEvent(event)

    def _event_push(self, request):
        pass

    def _event_pull_request(self, request):
        body = request.json_body
        action = body.get('action')
        pr_body = body.get('pull_request')
        user = pr_body.get('user')
        head = pr_body.get('head')
        base = pr_body.get('base')
        base_repo = base.get('repo')

        event = TriggerEvent()
        event.trigger_name = 'github'
        event.project_name = base_repo.get('full_name')

        event.url = self.connection.getGitUrl(event.project_name)
        event.change_url = pr_body.get('url')

        event.account = None

        event.change_number = body.get('number')
        event.ref = "refs/pull/" + str(pr_body.get('number')) + "/head"
        event.oldrev = base.get('sha')
        event.newrev = head.get('sha')

        event.type = 'pull-request'

        if action == 'opened':
            event.type = 'pr-opened'
        elif action == 'synchronize':
            event.type = 'pr-changed'
        elif action == 'closed':
            event.type = 'pr-closed'
        elif action == 'reopened':
            event.type = 'pr-reopened'
        elif action == 'assigned':
            return None
        elif action == 'unassigned':
            return None
        elif action == 'labeled':
            return None
        elif action == 'unlabeled':
            return None
        else:
            return None

        return event

    def _validate_signature(self, request):
        secret = self.connection.connection_config.get('webhook_token', None)
        if not secret:
            return True

        body = request.body
        try:
            request_signature = request.headers['X-Hub-Signature']
        except KeyError:
            raise webob.exc.HTTPUnauthorized(
                'Please specify a X-Hub-Signature header with secret.')

        payload_signature = 'sha1=' + hmac.new(secret,
                                               body,
                                               hashlib.sha1).hexdigest()

        log.debug("Payload Signature: {0}".format(str(payload_signature)))
        log.debug("Request Signature: {0}".format(str(request_signature)))
        if str(payload_signature) != str(request_signature):
            raise webob.exc.HTTPUnauthorized(
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

        return True


class GithubConnection(BaseConnection):
    driver_name = 'github'
    log = logging.getLogger("connection.github")

    def __init__(self, *args, **kwargs):
        super(GithubConnection, self).__init__(*args, **kwargs)
        self.github = None
        self._change_cache = {}

    def onLoad(self):
        self.webhook_listener = GithubWebhookListener(self)
        self._authenticateGithubAPI()
        self._startWebhookListener()

    def _authenticateGithubAPI(self):
        token = self.connection_config.get('api_token', None)
        if token is not None:
            self.github = github3.login(token)
            self.log.info("Github API Authentication successful.")
        else:
            self.github = None
            self.log.info(
                "No Github credentials found in zuul configuration, cannot "
                "authenticate.")

    def _startWebhookListener(self):
        if not self.webhook_listener.is_alive():
            self.webhook_listener.start()

    def maintainCache(self, relevant):
        for key, change in self._change_cache.items():
            if change not in relevant:
                del self._change_cache[key]

    def getGitUrl(self, project):
        url = 'https://%s/%s' % ("github.com", project)
        return url


def getSchema():
    github_connection = v.Any(str, v.Schema({}, extra=True))
    return github_connection
