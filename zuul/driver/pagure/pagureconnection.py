import logging
import hmac
import hashlib
import queue
import threading
import time
import json
import requests
import cherrypy
import traceback
import voluptuous as v

import gear

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController
from zuul.lib.config import get_default

from zuul.driver.pagure.paguremodel import PagureTriggerEvent, PullRequest

# Notes:
# Pagure project option: "Activate Only assignee can merge pull-request"
# https://docs.pagure.org/pagure/usage/project_settings.html?highlight=score#activate-only-assignee-can-merge-pull-request
# Idea would be to prevent PR merge by anybody else than Zuul.
# Pagure project option: "Activate Minimum score to merge pull-request"
# https://docs.pagure.org/pagure/usage/project_settings.html?highlight=score#activate-minimum-score-to-merge-pull-request
# API token seems limited to 60 days


def _sign_request(body, secret):
    signature = hmac.new(
        secret.encode('utf-8'), body, hashlib.sha1).hexdigest()
    return signature, body


class PagureGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.PagureGearmanWorker")

    def __init__(self, connection):
        self.config = connection.sched.config
        self.connection = connection
        self.thread = threading.Thread(target=self._run,
                                       name='pagure-gearman-worker')
        self._running = False
        handler = "pagure:%s:payload" % self.connection.connection_name
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
            "Pagure Webhook Received (id: %(msg_id)s, topic: %(topic)s)" % (
                payload))

        # TODO(fbo): Validate project in the request is a project we know

        try:
            self.__dispatch_event(payload)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling Pagure event:")

        return output

    def __dispatch_event(self, payload):
        event = payload['topic']
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
        self.gearman = gear.TextWorker('Zuul Pagure Connector')
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


class PagureEventConnector(threading.Thread):
    """Move events from Pagure into the scheduler"""

    log = logging.getLogger("zuul.PagureEventConnector")

    def __init__(self, connection):
        super(PagureEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False
        self.event_handler_mapping = {
            'pull-request.comment.added': self._event_issue_comment,
            'pull-request.new': self._event_pull_request,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return
        self.log.info("Received event: %s" % str(event_type))

        self.log.info(json_body)

        if event_type not in self.event_handler_mapping:
            message = "Unhandled X-Pagure-Event: %s" % event_type
            self.log.info(message)
            return

        try:
            event = self.event_handler_mapping[event_type](json_body)
        except Exception:
            self.log.exception(
                'Exception when handling event: %s' % event_type)
            event = None

        if event:
            if event.change_number:
                pass
                # project = self.connection.source.getProject(event.project_name)
                # self.connection._getChange(project,
                #                            event.change_number,
                #                            event.patch_number,
                #                            refresh=True)
            event.project_hostname = self.connection.canonical_hostname
            self.connection.logEvent(event)
            self.log.info(event)
            self.connection.sched.addEvent(event)

    def _event_base(self, body):
        data = body['msg']['pullrequest']
        event = PagureTriggerEvent()
        event.title = data.get('title')
        event.project_name = data.get('project', {}).get('name')
        event.change_number = data.get('id')
        event.updated_at = data.get('date_created')
        event.branch = data.get('branch')
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)

        event.ref = "refs/pull/%s/head" % event.change_number
        event.patch_number = data.get('commit_start')
        event.type = 'pull_request'
        return event, data

    def _event_issue_comment(self, body):
        """ Handles pull request comments """
        # https://fedora-fedmsg.readthedocs.io/en/latest/topics.html#pagure-pull-request-comment-added
        event, data = self._event_base(body)
        last_comment = data.get('comments', [])[-1]
        if last_comment.get('notification') is True:
            # Seems that an updated PR (new commits) triggers the comment.added
            # event. A message is added by pagure on the PR but notification
            # is set to true.
            # Also see issue: https://pagure.io/pagure/issue/3684
            event.action = 'edited'
        else:
            event.action = 'comment'
        # Assume last comment is the one that have triggered the event
        event.comment = last_comment.get('comment')
        return event

    def _event_pull_request(self, body):
        """ Handles pull request event """
        # https://fedora-fedmsg.readthedocs.io/en/latest/topics.html#pagure-pull-request-new
        event, data = self._event_base(body)
        event.action = 'opened'
        return event

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving Pagure event:")
            finally:
                self.connection.eventDone()


class PagureAPIClient():
    log = logging.getLogger("zuul.PagureAPIClient")

    def __init__(self, server, api_token=None):
        self.server = server
        self.session = requests.Session()
        self.base_url = 'https://%s/api/0/' % self.server
        self.api_token = api_token
        self.headers = {'Authorization': 'token %s' % self.api_token}

    def get(self, url):
        self.log.info("Getting resource %s ..." % url)
        ret = self.session.get(url)
        return ret.json()

    def post(self, url, params):
        self.log.info("Posting on resource %s, params (%s) ..." % (
            url, params))
        ret = requests.post(url, data=params, headers=self.headers)
        self.log.info("Post returned (code: %s): %s" % (
            ret.status_code, ret.text))
        return ret.json()

    def get_project_branches(self, project):
        path = '%s/git/branches' % project
        return self.get(self.base_url + path).get('branches', [])

    def get_pr(self, project, number):
        path = '%s/pull-request/%s' % (project, number)
        return self.get(self.base_url + path)

    def get_pr_diffstats(self, project, number):
        path = '%s/pull-request/%s/diffstats' % (project, number)
        return self.get(self.base_url + path)

    def get_commit_statuses(self, project, sha):
        # Flags are CI status in pagure
        # https://pagure.io/api/0/ # see - Flags for a commit
        # But unabled to use the api - request below don't work as expected
        # curl https://pagure.io/api/0/pagure/c/38ce9f52725faf94f316d169e1d978b24f26351a/flag
        # curl https://pagure.io/api/0/fork/farhaan/pagure/c/38ce9f52725faf94f316d169e1d978b24f26351a/flag
        # puiterwijk | fbo: that will return the flags for the commit, not the PR
        # puiterwijk | And in this case, the PR has flags, the commit doesn't
        # puiterwijk | I don't think there's an API call to get PR flags
        return []

    def comment_pull(self, project, number, message):
        params = {"comment": message}
        path = '%s/pull-request/%s/comment' % (project, number)
        return self.post(self.base_url + path, params)


class PagureConnection(BaseConnection):
    driver_name = 'pagure'
    log = logging.getLogger("zuul.PagureConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(PagureConnection, self).__init__(
            driver, connection_name, connection_config)
        self._change_cache = {}
        self.project_branch_cache = {}
        self.projects = {}
        self.server = self.connection_config.get('server', 'pagure.io')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.git_ssh_key = self.connection_config.get('sshkey')
        self.api_token = self.connection_config.get('api_token')
        self.pagure = PagureAPIClient(self.server, api_token=self.api_token)
        self.source = driver.getSource(self)
        self.event_queue = queue.Queue()

        self.sched = None

        self.installation_map = {}
        self.installation_token_cache = {}

    def onLoad(self):
        self.log.info('Starting Pagure connection: %s' % self.connection_name)
        self.gearman_worker = PagureGearmanWorker(self)
        self.log.info('Starting event connector')
        self._start_event_connector()
        self.log.info('Starting GearmanWorker')
        self.gearman_worker.start()

    def _start_event_connector(self):
        self.pagure_event_connector = PagureEventConnector(self)
        self.pagure_event_connector.start()

    def _stop_event_connector(self):
        if self.pagure_event_connector:
            self.pagure_event_connector.stop()
            self.pagure_event_connector.join()

    def addEvent(self, data, event):
        return self.event_queue.put((time.time(), data, event))

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()

    def maintainCache(self, relevant):
        remove = set()
        for key, change in self._change_cache.items():
            if change not in relevant:
                remove.add(key)
        for key in remove:
            del self._change_cache[key]

    def clearBranchCache(self):
        self._project_branch_cache_exclude_unprotected = {}
        self._project_branch_cache_include_unprotected = {}

    def getWebController(self, zuul_web):
        return PagureWebController(zuul_web, self)

    def validateWebConfig(self, config, connections):
        if 'webhook_token' not in self.connection_config:
            raise Exception(
                "webhook_token not found in config for connection %s" %
                self.connection_name)
        return True

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project

    def getPullUrl(self, project, number):
        return '%s/pull-request/%s' % (self.getGitwebUrl(project), number)

    def getGitwebUrl(self, project, sha=None):
        url = 'https://%s/%s' % (self.server, project)
        if sha is not None:
            url += '/commit/%s' % sha
        return url

    def getProjectBranches(self, project, tenant):
        branches = self.project_branch_cache.get(project.name)

        if branches is not None:
            return branches

        branches = self.pagure.get_project_branches(project.name)
        self.project_branch_cache['branches'] = branches

        return branches

    def getGitUrl(self, project):
        if self.git_ssh_key:
            return 'ssh://git@%s/%s.git' % (self.server, project.name)

        return 'https://%s/%s' % (self.server, project.name)

    def getChange(self, event, refresh=False):
        project = self.source.getProject(event.project_name)
        if event.change_number:
            change = self._getChange(
                project, event.change_number, refresh=refresh)
            change.url = event.change_url
            change.uris = [
                '%s/%s/pull/%s' % (self.server, project, change.number),
            ]
            change.source_event = event
            change.is_current_patchset = (change.pr.get('commit_start') ==
                                          event.patch_number)
        else:
            pass
            # if event.ref and event.ref.startswith('refs/tags/'):
            #     change = Tag(project)
            #     change.tag = event.ref[len('refs/tags/'):]
            # elif event.ref and event.ref.startswith('refs/heads/'):
            #     change = Branch(project)
            #     change.branch = event.ref[len('refs/heads/'):]
            # else:
            #     change = Ref(project)
            # change.ref = event.ref
            # change.oldrev = event.oldrev
            # change.newrev = event.newrev
            # change.url = self.getGitwebUrl(project, sha=event.newrev)
            # change.source_event = event
            # if hasattr(event, 'commits'):
            #     change.files = self.getPushedFileNames(event)
        return change

    def _getChange(self, project, number, refresh=False):
        key = (project.name, number)
        change = self._change_cache.get(key)
        if change and not refresh:
            return change
        if not change:
            change = PullRequest(project.name)
            change.project = project
            change.number = number
        self._change_cache[key] = change
        try:
            self._updateChange(change)
        except Exception:
            if key in self._change_cache:
                del self._change_cache[key]
            raise
        return change

    def getPull(self, project_name, number):
        pr = self.pagure.get_pr(project_name, number)
        diffstats = self.pagure.get_pr_diffstats(project_name, number)
        pr['files'] = diffstats.keys()
        # pr['labels'] = [l.name for l in issueobj.labels()]
        self.log.debug('Got PR %s#%s', project_name, number)
        return pr

    def getCommitStatuses(self, project, sha):
        statuses = self.pagure.get_commit_statuses(project, sha)
        self.log.debug("Got commit statuses for sha %s on %s", sha, project)
        return statuses

    def getStatuses(self, project, sha):
        statuses = self.getCommitStatuses(project.name, sha)
        return statuses

    def getPullReviews(self, project_name, pr):
        # Not clear yet, what we really need here. Do I need
        # the review details or simply the mergeability of a PR.
        # api/0/ does not offers a way to get that information
        # There is https://pagure.io/pv/pull-request/merge but it Seems
        # to not be part of the official api.
        return {}

    def _updateChange(self, change):
        self.log.info("Updating %s" % (change,))
        change.pr = self.getPull(change.project.name, change.number)
        change.ref = "refs/pull/%s/head" % change.number
        change.branch = change.pr.get('branch')
        change.files = change.pr.get('files')
        change.title = change.pr.get('title')
        change.open = change.pr.get('status') == 'Open'
        change.is_merged = change.pr.get('status') == 'Merged'
        change.status = self.getStatuses(change.project,
                                         change.patchset)
        change.reviews = self.getPullReviews(change.project,
                                             change.number)
        # change.labels = change.pr.get('labels')
        # ensure message is at least an empty string
        change.message = change.pr.get('body') or ''
        change.updated_at = change.pr.get('last_updated')

        if self.sched:
            self.sched.onChangeUpdated(change)

        return change

    def commentPull(self, project, pr_number, message):
        self.pagure.comment_pull(project, pr_number, message)
        self.log.debug("Commented on PR %s#%s", project, pr_number)


class PagureWebController(BaseWebController):

    log = logging.getLogger("zuul.PagureWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web
        self.token = self.connection.connection_config.get('webhook_token')

    def _validate_signature(self, body, headers):
        self.log.info("Received headers: %s" % str(headers))
        self.log.info("Received body: %s" % str(body))
        try:
            request_signature = headers['x-pagure-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'x-pagure-signature header missing.')

        signature, payload = _sign_request(body, self.token)

        self.log.info("Payload Signature: {0}".format(str(signature)))
        self.log.info("Request Signature: {0}".format(str(request_signature)))
        if not hmac.compare_digest(
            str(signature), str(request_signature)):
            raise cherrypy.HTTPError(
                401,
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

        return payload

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        # https://docs.pagure.org/pagure/usage/using_webhooks.html
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
    pagure_connection = v.Any(str, v.Schema(dict))
    return pagure_connection
