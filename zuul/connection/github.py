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

from paste import httpserver
import webob

from zuul.connection import BaseConnection
from zuul.model import TriggerEvent


class GithubWebhookListener(threading.Thread):

    log = logging.getLogger("zuul.connection.GithubWebhookListener")

    def __init__(self, scheduler, port=8002):
        self.scheduler = scheduler
        self.port = port
        self.server = httpserver.serve(webob.wsgify(self.app), host='0.0.0.0',
                                       port=self.port, start_loop=False)

    def run(self):
        self.server.serve_forever()

    def app(self, request):
        if request.path != '/payload':
            raise webob.exc.HTTPNotFound()

        if request.method != 'POST':
            raise webob.exc.HTTPInvalidMethod('Only POST method is allowed.')

        try:
            event = request.headers['X-Github-Event']
        except KeyError:
            raise webob.exc.HTTPBadRequest('Please specify a X-Github-Event '
                                           'header.')

        if event != 'pull_request':
            raise webob.exc.HTTPBadRequest('Only pull_request events '
                                           'are supported.')

        body = request.json_body
        # TODO(greghaynes) support synchronize action
        action = body['action']
        if action == 'opened':
            pr_body = body['pull_request']
            event = TriggerEvent()
            event.type = 'patchset-created'
            event.change_url = pr_body['url']
            self.scheduler.addEvent(event)
        else:
            pass


class GithubConnection(BaseConnection):

    def __init__(self, connection_name, connection_config):
        super(GithubConnection, self).__init__(self)

    def registerScheduler(self, scheduler):
        super(GithubWebhookListener, self).registerScheduler(scheduler)
        self.webhook_listener = GithubWebhookListener(scheduler)
        self.startWebhookListener()

    def startWebhookListener(self):
        if not self.webhook_listener.is_alive():
            self.webhook_listener.start()
