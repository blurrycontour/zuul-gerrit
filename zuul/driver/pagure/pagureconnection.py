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
            'pull-request.flag.added': self._event_flag_added,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return

        self.log.info("Received event: %s" % str(event_type))
        # self.log.debug("Event payload: %s " % json_body)

        if event_type not in self.event_handler_mapping:
            message = "Unhandled X-Pagure-Event: %s" % event_type
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
            if event.change_number:
                project = self.connection.source.getProject(event.project_name)
                self.connection._getChange(project,
                                           event.change_number,
                                           event.patch_number,
                                           refresh=True)
            event.project_hostname = self.connection.canonical_hostname
            self.connection.logEvent(event)
            self.log.info(event)
            self.connection.sched.addEvent(event)

    def _event_base(self, body):
        data = body['msg']['pullrequest']
        data['flag'] = body['msg'].get('flag')
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
        event.type = 'pg_pull_request'
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
            event.action = 'changed'
        else:
            if last_comment.get('comment', '').find(':thumbsup:') >= 0:
                event.action = 'thumbsup'
                event.type = 'pg_pull_request_review'
            elif last_comment.get('comment', '').find(':thumbsdown:') >= 0:
                event.action = 'thumbsdown'
                event.type = 'pg_pull_request_review'
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

    def _event_flag_added(self, body):
        """ Handles flag added event """
        # https://fedora-fedmsg.readthedocs.io/en/latest/topics.html#pagure-pull-request-flag-added
        event, data = self._event_base(body)
        event.status = data['flag']['status']
        event.action = 'status'
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
        self.log.debug("Getting resource %s ..." % url)
        ret = self.session.get(url)
        return ret.json()

    def post(self, url, params=None):
        self.log.info("Posting on resource %s, params (%s) ..." % (
            url, params))
        ret = requests.post(url, data=params, headers=self.headers)
        self.log.debug("Post returned (code: %s): %s" % (
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

    def get_pr_flags(self, project, number, last=False):
        # Cannot get PR flags https://pagure.io/pagure/issue/3962
        # path = '%s/pull-request/%s/flag' % (project, number)
        # data = self.get(self.base_url + path)
        data = {'flags': [{'status': 'success'}]}
        if last:
            return data['flags'][0]
        else:
            return data['flags']

    def set_pr_flag(self, project, number, status, url, description):
        params = {
            "username": "Zuul",
            "comment": "Jobs result is %s" % status,
            "status": status,
            "url": url}
        path = '%s/pull-request/%s/flag' % (project, number)
        return self.post(self.base_url + path, params)

    def get_commit_flags(self, project, sha):
        path = '%s/c/%s/flag' % (project, sha)
        return self.get(self.base_url + path)

    def set_commit_flag(self, project, sha, status):
        params = {
            "username": "Zuul",
            "comment": "Jobs result is %s" % status,
            "status": status,
            "url": "https://sftests.com/zuul/log"}
        path = '%s/c/%s/flag' % (project, sha)
        return self.post(self.base_url + path, params)

    def comment_pull(self, project, number, message):
        params = {"comment": message}
        path = '%s/pull-request/%s/comment' % (project, number)
        return self.post(self.base_url + path, params)

    def check_mergeability(self, project, number):
        # The thumbsup count ceil have an impact on 'cached_merge_status'
        # and if not reached then the status remain 'unknown'. Once reached
        # the status changed to 'MERGE' or 'FFORWARD'. It mights also
        # change to something like 'UNABLE TO MERGE' that we'll need to
        # take in account.
        # Not reliable when approval :thumbsup: or :thumbsdown: Only
        # the UI call refresh the cached_merge_status :(
        # https://pagure.io/pagure/issue/4002

        # pr = self.get_pr(project, number)
        # status = pr['cached_merge_status']
        # return True if status in ('MERGE', 'FFORWARD') else False

        raise NotImplementedError

    def merge_pr(self, project, number):
        # https://pagure.io/pagure/issue/3999  # 500 when change is in CONFLICT
        path = '%s/pull-request/%s/merge' % (project, number)
        return self.post(self.base_url + path)


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

        self.log.info("Got branches for %s" % project.name)
        return branches

    def getGitUrl(self, project):
        if self.git_ssh_key:
            return 'ssh://git@%s/%s.git' % (self.server, project.name)

        return 'https://%s/%s' % (self.server, project.name)

    def getChange(self, event, refresh=False):
        project = self.source.getProject(event.project_name)
        if event.change_number:
            self.log.info("Getting change for %s#%s" % (
                project, event.change_number))
            change = self._getChange(
                project, event.change_number, event.patch_number,
                refresh=refresh)
            change.url = event.change_url
            change.uris = [
                '%s/%s/pull/%s' % (self.server, project, change.number),
            ]
            change.source_event = event
            change.is_current_patchset = (change.pr.get('commit_start') ==
                                          event.patch_number)
        else:
            self.log.info("Getting change for %s ref:%s" % (
                project, event.ref))
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

    def _getChange(self, project, number, patchset=None, refresh=False):
        key = (project.name, number)
        change = self._change_cache.get(key)
        if change and not refresh:
            self.log.debug("Getting change from cache %s" % str(key))
            return change
        if not change:
            change = PullRequest(project.name)
            change.project = project
            change.number = number
            # patchset is the tips commit of the PR
            change.patchset = patchset
        self._change_cache[key] = change
        try:
            self.log.debug("Getting change from pagure pr#%s" % number)
            self._updateChange(change)
        except Exception:
            if key in self._change_cache:
                del self._change_cache[key]
            raise
        return change

    def _hasRequiredStatusChecks(self):
        # Here check CI flag - currently no get support on PR's flag on pagure.
        return True

    def canMerge(self, change, allow_needs):
        if not self._hasRequiredStatusChecks():
            return False

        # Pagure 5.1 is not reliable on that for now
        # can_merge = self.pagure.check_mergeability(
        #     change.project.name, change.number)

        # For now just assume if score is >= 1 then we naively say True
        can_merge = True

        self.log.info('Check PR %s#%s mergeability can_merge: %s' % (
            change.project.name, change.number, can_merge))
        return can_merge

    def getPull(self, project_name, number):
        pr = self.pagure.get_pr(project_name, number)
        diffstats = self.pagure.get_pr_diffstats(project_name, number)
        pr['files'] = diffstats.keys()
        self.log.info('Got PR %s#%s', project_name, number)
        return pr

    def getStatus(self, project, number):
        return self.getCommitStatus(project.name, number)

    def getScore(self, pr):
        score_board = {}
        last_pr_code_updated = 0
        # First get last PR updated date
        for comment in pr.get('comments', []):
            # PR updated are reported as comment but with the notification flag
            if comment['notification']:
                date = int(comment['date_created'])
                if date > last_pr_code_updated:
                    last_pr_code_updated = date
        # Now compute the score
        for comment in pr.get('comments', []):
            author = comment['user']['fullname']
            date = int(comment['date_created'])
            # Only handle score since the last PR update
            if date >= last_pr_code_updated:
                score_board.setdefault(author, 0)
                # Use the same strategy to compute the score than Pagure
                if comment.get('comment', '').find(':thumbsup:') >= 0:
                    score_board[author] += 1
                if comment.get('comment', '').find(':thumbsdown:') >= 0:
                    score_board[author] -= 1
        return sum(score_board.values())

    def _updateChange(self, change):
        self.log.info("Updating change from pagure %s" % change)
        change.pr = self.getPull(change.project.name, change.number)
        change.ref = "refs/pull/%s/head" % change.number
        change.branch = change.pr.get('branch')
        change.files = change.pr.get('files')
        change.title = change.pr.get('title')
        change.open = change.pr.get('status') == 'Open'
        change.is_merged = change.pr.get('status') == 'Merged'
        # TODO(fbo): Make sure to get the last status (CI flag status)
        change.status = self.getStatus(change.project, change.number)
        change.score = self.getScore(change.pr)
        change.message = change.pr.get('body') or ''
        # last_updated seems to be touch for comment changed/flags - that's OK
        change.updated_at = change.pr.get('last_updated')

        if self.sched:
            self.sched.onChangeUpdated(change)

        return change

    def commentPull(self, project, number, message):
        self.pagure.comment_pull(project, number, message)
        self.log.info("Commented on PR %s#%s", project, number)

    def setCommitStatus(self, project, number, state, url='',
                        description='', context=''):
        self.pagure.set_pr_flag(project, number, state, url, description)
        self.log.info("Set pull-request CI flag status : %s" % description)

    def getCommitStatus(self, project, number):
        _status = self.pagure.get_pr_flags(project, number, last=True)
        status = _status['status']
        self.log.info(
            "Got pull-request CI status for PR %s on %s status: %s", (
                number, project, status))
        return status

    def getChangesDependingOn(self, change, projects, tenant):
        """ Reverse lookup of PR depending on this one
        """
        # TODO(fbo) Need to check if there is a way to Query pagure to search
        # accross projects' PRs for a str in commit_start commit msg or PR
        # message body. Not a blocker for now.
        return []

    def mergePull(self, project, number):
        self.pagure.merge_pr(project, number)
        self.log.debug("Merged PR %s#%s", project, number)


class PagureWebController(BaseWebController):

    log = logging.getLogger("zuul.PagureWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web
        self.token = self.connection.connection_config.get('webhook_token')

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-pagure-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'x-pagure-signature header missing.')

        signature, payload = _sign_request(body, self.token)

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
