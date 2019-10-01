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
import threading
import json
import queue
import traceback
import cherrypy
import voluptuous as v
import gear
import time
import requests
from urllib.parse import quote_plus

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController
from zuul.lib.config import get_default

from zuul.driver.gitlab.gitlabmodel import GitlabTriggerEvent, MergeRequest


class GitlabGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.GitlabGearmanWorker")

    def __init__(self, connection):
        self.config = connection.sched.config
        self.connection = connection
        self.thread = threading.Thread(target=self._run,
                                       name='gitlab-gearman-worker')
        self._running = False
        handler = "gitlab:%s:payload" % self.connection.connection_name
        self.jobs = {
            handler: self.handle_payload,
        }

    def _run(self):
        while self._running:
            try:
                job = self.gearman.getJob()
                try:
                    if job.name not in self.jobs:
                        self.log.exception("Exception while running job")
                        job.sendWorkException(
                            traceback.format_exc().encode('utf8'))
                        continue
                    output = self.jobs[job.name](json.loads(job.arguments))
                    job.sendWorkComplete(json.dumps(output))
                except Exception:
                    self.log.exception("Exception while running job")
                    job.sendWorkException(
                        traceback.format_exc().encode('utf8'))
            except gear.InterruptedError:
                pass
            except Exception:
                self.log.exception("Exception while getting job")

    def handle_payload(self, args):
        payload = args["payload"]

        self.log.info(
            "Gitlab Webhook Received event kind: %(object_kind)s" % payload)

        try:
            self.__dispatch_event(payload)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling Gitlab event:")

        return output

    def __dispatch_event(self, payload):
        self.log.info(payload)
        event = payload['object_kind']
        try:
            self.log.info("Dispatching event %s" % event)
            self.connection.addEvent(payload, event)
        except Exception as err:
            message = 'Exception dispatching event: %s' % str(err)
            self.log.exception(message)
            raise Exception(message)

    def start(self):
        self._running = True
        server = self.config.get('gearman', 'server')
        port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        self.gearman = gear.TextWorker('Zuul Gitlab Connector')
        self.log.debug("Connect to gearman")
        self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca)
        self.log.debug("Waiting for server")
        self.gearman.waitForServer()
        self.log.debug("Registering")
        for job in self.jobs:
            self.gearman.registerFunction(job)
        self.thread.start()

    def stop(self):
        self._running = False
        self.gearman.stopWaitingForJobs()
        # We join here to avoid whitelisting the thread -- if it takes more
        # than 5s to stop in tests, there's a problem.
        self.thread.join(timeout=5)
        self.gearman.shutdown()


class GitlabEventConnector(threading.Thread):
    """Move events from Gitlab into the scheduler"""

    log = logging.getLogger("zuul.GitlabEventConnector")

    def __init__(self, connection):
        super(GitlabEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False
        self.event_handler_mapping = {
            'merge_request': self._event_merge_request,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _event_merge_request(self, body):
        event = GitlabTriggerEvent()
        attrs = body['object_attributes']
        event.title = attrs['title']
        event.updated_at = attrs['updated_at']
        event.project_name = body['project']['path_with_namespace']
        event.change_number = attrs['iid']
        event.branch = attrs['target_branch']
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)
        event.ref = "refs/merge-requests/%s/head" % event.change_number
        event.patch_number = attrs['last_commit']['id']
        if event.updated_at == attrs['updated_at']:
            event.action = 'opened'
        else:
            event.action = 'changed'
        event.type = 'gl_pull_request'
        return event

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return

        self.log.info("Received event: %s" % str(event_type))

        if event_type not in self.event_handler_mapping:
            message = "Unhandled Gitlab event: %s" % event_type
            self.log.info(message)
            return

        if event_type in self.event_handler_mapping:
            self.log.debug("Handling event: %s" % event_type)

        try:
            event = self.event_handler_mapping[event_type](json_body)
        except Exception:
            self.log.exception(
                'Exception when handling event: %s' % event_type)
            event = None

        if event:
            event.timestamp = ts
            if event.change_number:
                project = self.connection.source.getProject(event.project_name)
                self.connection._getChange(project,
                                           event.change_number,
                                           event.patch_number,
                                           refresh=True,
                                           url=event.change_url,
                                           event=event)
            event.project_hostname = self.connection.canonical_hostname
            self.connection.logEvent(event)
            self.connection.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving Gitlab event:")
            finally:
                self.connection.eventDone()


class GitlabAPIClient():
    log = logging.getLogger("zuul.GitlabAPIClient")

    def __init__(self, baseurl, api_token):
        self.session = requests.Session()
        self.baseurl = '%s/api/v4/' % baseurl
        self.api_token = api_token
        self.headers = {'Authorization': 'Authorization: Bearer %s' % (
            self.api_token)}

    def get_mr(self, project_name, number):
        ret = self.session.get("%s/projects/%s/merge_requests/%s" % (
            self.baseurl, quote_plus(project_name), number))
        return ret.json()


class GitlabConnection(BaseConnection):
    driver_name = 'gitlab'
    log = logging.getLogger("zuul.GitlabConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(GitlabConnection, self).__init__(
            driver, connection_name, connection_config)
        self.projects = {}
        self._change_cache = {}
        self.server = self.connection_config.get('server', 'gitlab.com')
        self.baseurl = self.connection_config.get(
            'baseurl', 'https://%s' % self.server).rstrip('/')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.webhook_token = self.connection_config.get(
            'webhook_token', '')
        self.api_token = self.connection_config.get(
            'api_token', '')
        self.gl_client = GitlabAPIClient(self.baseurl, self.api_token)
        self.sched = None
        self.event_queue = queue.Queue()
        self.source = driver.getSource(self)

    def _start_event_connector(self):
        self.gitlab_event_connector = GitlabEventConnector(self)
        self.gitlab_event_connector.start()

    def _stop_event_connector(self):
        if self.gitlab_event_connector:
            self.gitlab_event_connector.stop()
            self.gitlab_event_connector.join()

    def onLoad(self):
        self.log.info('Starting Gitlab connection: %s' % self.connection_name)
        self.gearman_worker = GitlabGearmanWorker(self)
        self.log.info('Starting event connector')
        self._start_event_connector()
        self.log.info('Starting GearmanWorker')
        self.gearman_worker.start()

    def onStop(self):
        if hasattr(self, 'gearman_worker'):
            self.gearman_worker.stop()
            self._stop_event_connector()

    def addEvent(self, data, event=None):
        return self.event_queue.put((time.time(), data, event))

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()

    def getWebController(self, zuul_web):
        return GitlabWebController(zuul_web, self)

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project

    def getGitwebUrl(self, project, sha=None):
        url = '%s/%s' % (self.baseurl, project)
        if sha is not None:
            url += '/tree/%s' % sha
        return url

    def getPullUrl(self, project, number):
        return '%s/%s/merge_requests/%s' % (self.baseurl, project, number)

    def getChange(self, event, refresh=False):
        project = self.source.getProject(event.project_name)
        if event.change_number:
            self.log.info("Getting change for %s#%s" % (
                project, event.change_number))
            change = self._getChange(
                project, event.change_number, event.patch_number,
                refresh=refresh, event=event)
            change.source_event = event
            change.is_current_patchset = (change.pr.get('commit_stop') ==
                                          event.patch_number)
        else:
            self.log.info("Getting change for %s ref:%s" % (
                project, event.ref))
            raise NotImplementedError
        return change

    def _getChange(self, project, number, patchset=None,
                   refresh=False, url=None, event=None):
        key = (project.name, number, patchset)
        change = self._change_cache.get(key)
        if change and not refresh:
            self.log.debug("Getting change from cache %s" % str(key))
            return change
        if not change:
            change = MergeRequest(project.name)
            change.project = project
            change.number = number
            # patchset is the tips commit of the PR
            change.patchset = patchset
            change.url = url
            change.uris = list(url)
        self._change_cache[key] = change
        try:
            self.log.debug("Getting change mr#%s from project %s" % (
                number, project.name))
            self._updateChange(change, event)
        except Exception:
            if key in self._change_cache:
                del self._change_cache[key]
            raise
        return change

    def _updateChange(self, change, event):
        self.log.info("Updating change from Gitlab %s" % change)
        change.mr = self.getPull(change.project.name, change.number)
        # change.ref = "refs/pull/%s/head" % change.number
        # change.branch = change.pr.get('branch')
        # change.patchset = change.pr.get('commit_stop')
        # change.files = change.pr.get('files')
        # change.title = change.pr.get('title')
        # change.tags = change.pr.get('tags')
        # change.open = change.pr.get('status') == 'Open'
        # change.is_merged = change.pr.get('status') == 'Merged'
        # change.status = self.getStatus(change.project, change.number)
        # change.score = self.getScore(change.pr)
        # change.message = change.pr.get('initial_comment') or ''
        # last_updated seems to be touch for comment changed/flags - that's OK
        change.updated_at = change.pr.get('last_updated')
        self.log.info("Updated change from Gitlab %s" % change)

        if self.sched:
            self.sched.onChangeUpdated(change, event)

        return change

    def getPull(self, project_name, number):
        mr = self.gl_client.get_mr(project_name, number)
        self.log.info('Got MR %s#%s', project_name, number)
        return mr


class GitlabWebController(BaseWebController):

    log = logging.getLogger("zuul.GitlabWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    def _validate_token(self, headers):
        try:
            event_token = headers['x-gitlab-token']
        except KeyError:
            raise cherrypy.HTTPError(401, 'x-gitlab-token header missing.')

        configured_token = self.connection.webhook_token
        if not configured_token == event_token:
            self.log.debug(
                "Missmatch (Incoming token: %s, Configured token: %s)" % (
                    event_token, configured_token))
            raise cherrypy.HTTPError(
                401,
                'Token does not match the server side configured token')

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        self.log.info("Event header: %s" % headers)
        self.log.info("Event body: %s" % body)
        self._validate_token(headers)
        json_payload = json.loads(body.decode('utf-8'))

        job = self.zuul_web.rpc.submitJob(
            'gitlab:%s:payload' % self.connection.connection_name,
            {'payload': json_payload})

        return json.loads(job.data[0])


def getSchema():
    return v.Any(str, v.Schema(dict))
