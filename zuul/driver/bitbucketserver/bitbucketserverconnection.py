import logging
import threading
import json
import queue
import cherrypy
import requests
import voluptuous as v
import time
import uuid

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController
from zuul.lib.logutil import get_annotated_logger

from zuul.driver.bitbucketserver.bitbucketservergearman import BitbucketServerGearmanWorker
from zuul.driver.bitbucketserver.bitbucketservermodel import BitbucketServerTriggerEvent


class BitbucketServerEventConnector(threading.Thread):
    """Move events from Bitbucket Server into the scheduler"""

    log = logging.getLogger("zuul.BitbucketServerEventConnector")

    def __init__(self, connection):
        super(BitbucketServerEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False

        self.event_handler_mapping = {
            'diagnostics:ping': self._event_ping,
            'repo:refs_changed': self._event_,
            'repo:modified': self._event_,
            'repo:fork': self._event_,
            'repo:comment:added': self._event_,
            'repo:comment:edited': self._event_,
            'repo:comment:deleted': self._event_,
            'mirror:repo_synchronized': self._event_,
            'pr:opened': self._event_,
            'pr:from_ref_updated': self._event_,
            'pr:modified': self._event_,
            'pr:reviewer:updated': self._event_,
            'pr:reviewer:approved': self._event_,
            'pr:reviewer:needs_work': self._event_,
            'pullrequest:fulfilled': self._event_,
            'pr:declined': self._event_,
            'pr:deleted': self._event_,
            'pr:comment:added': self._event_,
            'pr:comment:edited': self._event_,
            'pr:comment:deleted': self._event_,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _event_base(self, body):
        event = BitbucketServerTriggerEvent()
        event.project_name = body['repository']['project']['key'] + body['repository']['slug']
        return event

    def _event_ping(self, _):
        # Ping is the dummy event that can be triggered from Bitbucket UI.
        return None

    def _event_(self, body):
        raise NotImplementedError()

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return

        self.log.info("Received event: %s" % str(event_type))

        if event_type not in self.event_handler_mapping:
            message = "Unhandled BitbucketServer event: %s" % event_type
            self.log.info(message)
            return

        self.log.debug("Handling event: %s" % event_type)
        try:
            event = self.event_handler_mapping[event_type](json_body)
        except Exception:
            self.log.exception('Exception when handling event: %s' % event_type)
            event = None

        if event:
            event.zuul_event_id = str(uuid.uuid4())
            event.timestamp = ts
            self.connection.logEvent(event)
            self.connection.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving BitbucketServer event:")
            finally:
                self.connection.eventDone()


class BitbucketServerAPIClient(object):
    # https://docs.atlassian.com/bitbucket-server/rest/7.5.2/bitbucket-rest.html
    log = logging.getLogger("zuul.BitbucketServerAPIClient")

    def __init__(self, baseurl, username, password):
        self.session = requests.Session()
        self.baseurl = f'{baseurl}/rest/api/1.0/'

    def _manage_error(self, data, code, url, verb, zuul_event_id=None):
        raise NotImplementedError()

    def get(self, url, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        log.debug("Getting resource %s ..." % url)
        ret = self.session.get(url, headers=self.headers)
        log.debug("GET returned (code: %s): %s" % (ret.status_code, ret.text))
        return ret.json(), ret.status_code, ret.url, 'GET'

    def post(self, url, params=None, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        log.info("Posting on resource %s, params (%s) ..." % (url, params))
        ret = self.session.post(url, data=params, headers=self.headers)
        log.debug("POST returned (code: %s): %s" % (ret.status_code, ret.text))
        return ret.json(), ret.status_code, ret.url, 'POST'

    def put(self, url, params=None, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        log.info("Put on resource %s, params (%s) ..." % (url, params))
        ret = self.session.put(url, data=params, headers=self.headers)
        log.debug("PUT returned (code: %s): %s" % (ret.status_code, ret.text))
        return ret.json(), ret.status_code, ret.url, 'PUT'


class BitbucketServerConnection(BaseConnection):
    driver_name = 'bitbucketserver'
    log = logging.getLogger("zuul.BitbucketServerConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(BitbucketServerConnection, self).__init__(driver, connection_name, connection_config)

        self.projects = {}
        self.project_branch_cache = {}
        self._change_cache = {}

        if 'baseurl' not in self.connection_config:
            raise Exception(f'baseurl is required for Bitbucket connections in {self.connection_name}')
        self.baseurl = self.connection_config.get('baseurl', 'https://bitbucket:7990')

        self.user = self.connection_config.get('user', '')
        self.password = self.connection_config.get('password', '')

        self.bb_client = BitbucketServerAPIClient(self.baseurl, self.user, self.password)
        self.sched = None
        self.event_queue = queue.Queue()
        self.source = driver.getSource(self)

    def _start_event_connector(self):
        self.bitbucketserver_event_connector = BitbucketServerEventConnector(self)
        self.bitbucketserver_event_connector.start()

    def _stop_event_connector(self):
        if self.bitbucketserver_event_connector:
            self.bitbucketserver_event_connector.stop()
            self.bitbucketserver_event_connector.join()

    def onLoad(self):
        self.log.info('Starting BitbucketServer connection: %s' % self.connection_name)
        self.gearman_worker = BitbucketServerGearmanWorker(self)
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
        return BitbucketServerWebController(zuul_web, self)

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project

    def clearBranchCache(self):
        self.project_branch_cache = {}

    def getGitwebUrl(self, project_key, repo_slug, sha=None):
        url = f'{self.baseurl}/projects/{project_key}/repos/{repo_slug}'
        if sha:
            url += f'?at={sha}'
        return url

    def getPRUrl(self, project_key, repo_slug, number):
        return f'{self.baseurl}/projects/{project_key}/repos/{repo_slug}/pull-requests/{number}'

    def getGitUrl(self, project_key, repo_slug):
        return f'{self.baseurl}/scm/{project_key}/{repo_slug}.git'

    def getChange(self, event, refresh=False):
        raise NotImplementedError()

    def canMerge(self, change, allow_needs, event=None):
        raise NotImplementedError()

    def getPR(self, project_name, number, event=None):
        raise NotImplementedError()

    def commentPR(self, project_name, number, message, event=None):
        raise NotImplementedError()

    def approvePR(self, project_name, number, approve, event=None):
        raise NotImplementedError()

    def mergePR(self, project_name, number, event=None):
        raise NotImplementedError()


class BitbucketServerWebController(BaseWebController):
    log = logging.getLogger("zuul.BitbucketServerWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        self.log.info("Event header: %s" % headers)
        self.log.info("Event body: %s" % body)
        json_payload = json.loads(body.decode('utf-8'))
        json_payload['event'] = headers['x-event-key']
        json_payload['request_id'] = headers['x-request-id']
        job = self.zuul_web.rpc.submitJob(
            f'bitbucketserver:{self.connection.connection_name}:payload',
            {'payload': json_payload}
        )
        return json.loads(job.data[0])


def getSchema():
    return v.Any(str, v.Schema(dict))
