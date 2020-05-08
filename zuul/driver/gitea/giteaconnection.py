# Copyright 2018, 2019 Red Hat, Inc.
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
import queue
import threading
import time
import re
import json
import requests
import cherrypy
import traceback
import voluptuous as v
import giteapy

import gear

from zuul.connection import BaseConnection
from zuul.lib.logutil import get_annotated_logger
from zuul.web.handler import BaseWebController
from zuul.lib.config import get_default
from zuul.model import Ref, Branch, Tag, Project
from zuul.lib import dependson

from zuul.driver.gitea.giteamodel import GiteaTriggerEvent, PullRequest

# Minimal Gitea version supported 5.3.0
#
# Gitea is similar to Github as it handles PullRequest where PR is a branch
# composed of one or more commits. A PR can be commented, evaluated, updated,
# CI flagged, and merged. A PR can be flagged (success/failure/pending) and
# this driver uses that capability.
#
# PR approval can be driven by (evaluation). This is done via comments that
# contains a :thumbsup: or :thumbsdown:. Gitea computes a score based on
# that and allows or not the merge of PR if the "minimal score to merge" is
# set in repository settings.
#
# PR approval can be also driven via PR metadata flag.
#
# This driver expects to receive repository events via webhooks and
# do event validation based on the source IP address of the event.
#
# The driver connection needs an user's API token with
# - "Merge a pull-request"
# - "Flag a pull-request"
# - "Comment on a pull-request"
#
# On each project to be integrated with Zuul needs:
#
# The web hook target must be (in repository settings):
# - http://<zuul-web>/api/connection/<conn-name>/payload
#
# Repository settings (to be checked):
# - Minimum score to merge pull-request = 0 or -1
# - Notify on pull-request flag
# - Pull requests
# - Open metadata access to all (unchecked if approval)
#
# To define the connection in /etc/zuul/zuul.conf:
# [connection gitea.io]
# driver=gitea
# server=gitea.io
# baseurl=https://gitea.io
# api_token=QX29SXAW96C2CTLUNA5JKEEU65INGWTO2B5NHBDBRMF67S7PYZWCS0L1AKHXXXXX
# source_whitelist=8.43.85.75
#
# Current Non blocking issues:
# - Gitea does not reset the score when a PR code is updated
#   https://gitea.io/gitea/issue/3985
# - CI status flag updated field unit is second, better to have millisecond
#   unit to avoid unpossible sorting to get last status if two status set the
#   same second.
#   https://gitea.io/gitea/issue/4402
# - Zuul needs to be able to search commits that set a dependency (depends-on)
#   to a specific commit to reset jobs run when a dependency is changed. On
#   Gerrit and Github search through commits message is possible and used by
#   Zuul. Gitea does not offer this capability.

# Side notes
# - Idea would be to prevent PR merge by anybody else than Zuul.
# Gitea project option: "Activate Only assignee can merge pull-request"
# https://docs.gitea.org/gitea/usage/project_settings.html?highlight=score#activate-only-assignee-can-merge-pull-request


def _sign_request(body, secret):
    signature = hmac.new(
        secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return signature, body


class GiteaGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.GiteaGearmanWorker")

    def __init__(self, connection):
        self.config = connection.sched.config
        self.connection = connection
        self.thread = threading.Thread(target=self._run,
                                       name='gitea-gearman-worker')
        self._running = False
        handler = "gitea:%s:payload" % self.connection.connection_name
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
        event = args["event"]

        self.log.info(
            "Gitea Webhook Received (event: %s)" % event)

        try:
            self.__dispatch_event(event, payload)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling Gitea event:")

        return output

    def __dispatch_event(self, event, payload):
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
        self.gearman = gear.TextWorker('Zuul Gitea Connector')
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


class GiteaEventConnector(threading.Thread):
    """Move events from Gitea into the scheduler"""

    log = logging.getLogger("zuul.GiteaEventConnector")

    def __init__(self, connection):
        super(GiteaEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False
        self.event_handler_mapping = {
            'pull_request': self._event_pull_request,
            'push': self._event_push,
            'issue_comment': self._event_issue_comment,
            'pull_request_rejected': self._event_pull_request,
            'pull_request_approved': self._event_pull_request
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return

        self.log.info("Received event: %s" % str(event_type))
        self.log.debug("Event payload: %s " % json_body)

        if event_type not in self.event_handler_mapping:
            message = "Unhandled X-Gitea-Event: %s" % event_type
            self.log.info(message)
            return

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

    def _event_base(self, body) -> GiteaTriggerEvent:
        event = GiteaTriggerEvent()
        repo = body.get('repository')
        event.project_name = repo.get('full_name')
        return event

    def _event_push(self, body):
        """ Handles ref updated """
        event = self._event_base(body)
        event.ref = body.get('ref')
        BRANCH_REF_PREFIX = 'refs/heads/'
        if event.ref.startswith(BRANCH_REF_PREFIX):
            event.branch = event.ref[len(BRANCH_REF_PREFIX):]
        event.newrev = body.get('after')
        event.oldrev = body.get('before')
        if event.oldrev != event.newrev:
            event.branch_updated = True
        event.type = 'push'
        return event

    def _event_pull_request(self, body):
        """ Handles pull request events """
        event = self._event_base(body)
        pr = body.get('pull_request')
        event.title = pr.get('title')
        event.change_number = pr.get('number')
        event.change_url = pr.get('html_url')
        event.updated_at = pr.get('updated_at')
        event.branch = pr.get('head').get('label')
        event.ref = "refs/pull/%s/head" % event.change_number
        event.labels = [label.get('name') for label in pr.get('labels')]
        event.patch_number = pr.get('head').get('sha') # commit hash

        action = body.get('action')
        if action == 'opened':
            event.action = 'opened'
        elif action == 'reviewed':
            review = body.get('review')
            event.action = {
                'pull_request_review_rejected': 'rejected',
                'pull_request_review_approved': 'approved'
            }.get(review.get('type'))
        elif action == 'label_updated':
            event.action = 'labeled'
            # TODO: compare with previous and detect unlabeled events
        else:
            self.log.warn("Unknown PR action: %s", action)
            return None
        event.type = 'pull_request'
        return event
    
    def _event_issue_comment(self, body):
        """ Handles pull request comments """
        if body.get('is_pull') == False:
            return None
        event = self._event_base(body)
        comment = body.get('comment')
        event.comment = comment.get('body')
        event.type = 'pull_request'
        event.action = 'comment'
        return event


    ## start stuff just copied from pagure
    def _event_issue_initial_comment(self, body):
        """ Handles pull request initial comment change """
        event = self._event_base(body)
        event.action = 'changed'
        return event

    def _event_pull_request_tags_changed(self, body):
        """ Handles pull request metadata change """
        # pull-request.tag.added/removed use pull_request in payload body
        event = self._event_base(body)
        event.action = 'tagged'
        return event

    def _event_pull_request_closed(self, body):
        """ Handles pull request closed event """
        event = self._event_base(body)
        event.action = 'closed'
        return event

    def _event_flag_added(self, body):
        """ Handles flag added event """
        # https://fedora-fedmsg.readthedocs.io/en/latest/topics.html#gitea-pull-request-flag-added
        event = self._event_base(body)
        event.status = data['flag']['status']
        event.action = 'status'
        return event

    def _event_tag_created(self, body):
        event = self._event_base(body)
        event.project_name = data.get('project_fullname')
        event.tag = data.get('tag')
        event.ref = 'refs/tags/%s' % event.tag
        event.oldrev = None
        event.newrev = data.get('rev')
        return event

    def _event_ref_created(self, body):
        """ Handles ref created """
        event = self._event_base(body)
        event.project_name = data.get('project_fullname')
        event.branch = data.get('branch')
        event.ref = 'refs/heads/%s' % event.branch
        event.newrev = data.get('rev')
        event.oldrev = '0' * 40
        event.branch_created = True
        self.connection.project_branch_cache[
            event.project_name].append(event.branch)
        return event

    def _event_ref_deleted(self, body):
        """ Handles ref deleted """
        event = self._event_base(body)
        event.project_name = data.get('project_fullname')
        event.branch = data.get('branch')
        event.ref = 'refs/heads/%s' % event.branch
        event.oldrev = data.get('rev')
        event.newrev = '0' * 40
        event.branch_deleted = True
        self.connection.project_branch_cache[
            event.project_name].remove(event.branch)
        return event

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving Gitea event:")
            finally:
                self.connection.eventDone()


class GiteaAPIClientException(Exception):
    pass

### To refactor and add error handling!
def projectToOwnerAndName(project: Project) -> (str, str):
    parts = project.name.split("/", maxsplit=2)
    return (parts[0], parts[1])

class GiteaConnection(BaseConnection):
    driver_name = 'gitea'
    log = logging.getLogger("zuul.GiteaConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(GiteaConnection, self).__init__(
            driver, connection_name, connection_config)
        self.projects = {}
        self.server = self.connection_config.get('server', 'gitea.com')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.git_ssh_key = self.connection_config.get('sshkey')
        self.api_token = self.connection_config.get('api_token')
        self.webhook_secret = self.connection_config.get('webhook_secret')
        self.baseurl = self.connection_config.get(
            'baseurl', 'https://%s' % self.server).rstrip('/')
        self.cloneurl = self.connection_config.get(
            'cloneurl', self.baseurl).rstrip('/')
        self.source_whitelist = self.connection_config.get(
            'source_whitelist', '').split(',')
        self.source = driver.getSource(self)
        self.event_queue = queue.Queue()
        self.sched = None

    def onLoad(self):
        self.log.info('Starting Gitea connection: %s' % self.connection_name)
        self.gearman_worker = GiteaGearmanWorker(self)
        self.log.info('Starting event connector')
        self._start_event_connector()
        self.log.info('Starting GearmanWorker')
        self.gearman_worker.start()

    def _start_event_connector(self):
        self.gitea_event_connector = GiteaEventConnector(self)
        self.gitea_event_connector.start()

    def _stop_event_connector(self):
        if self.gitea_event_connector:
            self.gitea_event_connector.stop()
            self.gitea_event_connector.join()

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

    def get_project_api_client(self, project: str) -> giteapy.ApiClient:
        self.log.debug("Building project %s api_client" % project)
        config = giteapy.Configuration()
        config.host = self.baseurl + "/api/v1"
        if self.api_token != None:
            config.api_key["access_token"] = self.api_token
        return giteapy.ApiClient(config)

    def getWebController(self, zuul_web):
        return GiteaWebController(zuul_web, self)

    def validateWebConfig(self, config, connections):
        return True

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project: Project):
        self.projects[project.name] = project

    def getPullUrl(self, project: Project, number):
        #TODO use API to be correct
        return '%s/pulls/%s' % (self.getGitwebUrl(project), number)

    def getGitwebUrl(self, project: Project, sha=None):
        #TODO use API to be correct
        url = '%s/%s' % (self.baseurl, project)
        if sha is not None:
            url += '/commit/%s' % sha
        return url

    def getProjectBranches(self, project: Project, tenant):
        api = giteapy.RepositoryApi(self.get_project_api_client(project))
        owner, repo = projectToOwnerAndName(project)
        branches = api.repo_list_branches(owner, repo)

        self.log.info("Got branches for %s" % project)
        return [branch.name for branch in branches]

    def getGitUrl(self, project: Project):
        #TODO use API (https_url or ssh_url) to be correct
        return '%s/%s' % (self.cloneurl, project.name)

    def getChange(self, event, refresh=False):
        project = self.source.getProject(event.project_name)
        if event.change_number:
            self.log.info("Getting change for %s#%s" % (
                project, event.change_number))
            change = self._getChange(
                project, event.change_number, event.patch_number,
                refresh=refresh, event=event)
            change.source_event = event
            change.is_current_patchset = (change.pr.head.sha ==
                                          event.patch_number)
        else:
            self.log.info("Getting change for %s ref:%s" % (
                project, event.ref))
            if event.ref and event.ref.startswith('refs/tags/'):
                change = Tag(project)
                change.tag = event.tag
                change.branch = None
            elif event.ref and event.ref.startswith('refs/heads/'):
                change = Branch(project)
                change.branch = event.branch
            else:
                change = Ref(project)
                change.branch = None
            change.ref = event.ref
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.url = self.getGitwebUrl(project, sha=event.newrev)

            # Gitea does not send files details in the git-receive event.
            # Explicitly set files to None and let the pipelines processor
            # call the merger asynchronuously
            change.files = None

            change.source_event = event

        return change

    def _getChange(self, project: Project, number, patchset=None,
                   refresh=False, url=None, event=None):
        change = PullRequest(project.name)
        change.project = project
        change.number = number
        # patchset is the tips commit of the PR
        change.patchset = patchset
        change.url = url
        change.uris = [
            '%s/%s/pull/%s' % (self.baseurl, project, number),
        ]
        try:
            self.log.debug("Getting change pr#%s from project %s" % (
                number, project.name))
            self._updateChange(change, event)
        except Exception:
            raise
        return change

    def _hasRequiredStatusChecks(self, change):
        #gitea = self.get_project_api_client(change.project.name)
        #flag = gitea.get_pr_flags(change.number, last=True)
        #return True if flag.get('status', '') == 'success' else False
        #TODO(veecue) figure out how to do this (maybe need to get commit hash and then commit status)
        return True

    def canMerge(self, change, allow_needs, event=None):
        log = get_annotated_logger(self.log, event)
        gitea = self.get_project_api_client(change.project.name)
        api = giteapy.RepositoryApi(gitea)
        owner, name = projectToOwnerAndName(change.project)
        pr = api.repo_get_pull_request(owner, name, change.number)

        mergeable = pr.mergeable

        ci_flag = False
        if self._hasRequiredStatusChecks(change):
            ci_flag = True

        # TODO(gitea) Gitea does not expose code-reviews in the API
        #threshold = pr.get('threshold_reached')
        #if threshold is None:
        #    threshold = True

        log.debug(
            'PR %s#%s mergeability details mergeable: %s ', change.project.name, change.number,  mergeable)
        #    'flag: %s threshold: %s', change.project.name, change.number,
        #    mergeable, ci_flag, threshold)

        can_merge = mergeable and ci_flag # and threshold

        log.info('Check PR %s#%s mergeability can_merge: %s',
                 change.project.name, change.number, can_merge)
        return can_merge

    def getPull(self, project_name: Project, number) -> giteapy.PullRequest:
        gitea = self.get_project_api_client(project_name)
        api = giteapy.RepositoryApi(gitea)
        owner, name = projectToOwnerAndName(project_name)
        pr = api.repo_get_pull_request(owner, name, number)
        #diffstats = gitea.get_pr_diffstats(number)
        #pr['files'] = diffstats.keys()
        # TODO diffstats not exposed via API, maybe get them form patch file?
        self.log.info('Got PR %s#%s', project_name, number)
        return pr

    def getStatus(self, project: Project, number):
        return self.getCommitStatus(project, number)

    def getScore(self, pr):
        # TODO use some newly-created gitea API for this
        return 0

    def _updateChange(self, change: PullRequest, event):
        # Needs to be rewritten for gitea
        self.log.info("Updating change from gitea %s" % change)
        change.pr = self.getPull(change.project, change.number)
        change.ref = "refs/pull/%s/head" % change.number
        change.branch = change.pr.head.ref
        change.patchset = change.pr.head.sha
        #change.files = change.pr.get('files')
        change.title = change.pr.title
        change.labels = [label.name for label in change.pr.labels]
        change.open = change.pr.state == 'open'
        change.is_merged = change.pr.merged
        change.status = self.getStatus(change.project, change.number)
        change.score = self.getScore(change.pr)
        change.message = change.pr.body
        # last_updated seems to be touch for comment changed/flags - that's OK
        change.updated_at = change.pr.updated_at
        self.log.info("Updated change from gitea %s" % change)

        if self.sched:
            self.sched.onChangeUpdated(change, event)

        return change

    def commentPull(self, project: Project, number, message):
        api = giteapy.IssueApi(self.get_project_api_client(project))
        owner, repo = projectToOwnerAndName(project)
        api.issue_create_comment(owner, repo, number, body=giteapy.CreateIssueCommentOption(
            body=message
        ))
        self.log.info("Commented on PR %s#%s", project, number)

    def setCommitStatus(self, project: Project, number, state, url='',
                        description='', context=''):
        api = giteapy.RepositoryApi(self.get_project_api_client(project))
        owner, repo = projectToOwnerAndName(project)
        commit = self.getPull(project, number).head.sha
        body = giteapy.CreateStatusOption(
            context=context,
            description=description,
            state=state,
            target_url=url,
        )
        api.repo_create_status(owner, repo, commit, body=body)
        self.log.info("Set pull-request CI flag status : %s" % description)
        # Wait for 1 second as flag timestamp is by second
        time.sleep(1)

    def getCommitStatus(self, project: Project, number):
        api = giteapy.RepositoryApi(self.get_project_api_client(project))
        owner, repo = projectToOwnerAndName(project)
        sha = self.getPull(project, number).head.sha
        statuses = api.repo_list_statuses(owner, repo, sha, sort='recentupdate')
        context_successes = {}
        for status in statuses:
            if not status.context in context_successes:
                context_successes[status.context] = status.status == 'success'
        #TODO figure out required contexts (maybe repo_get_combined_status_by_ref does what we want?)
        #TODO(veecue) parse all statuses and check if for every context, the latest one was sucess
        self.log.info(
            "Got pull-request CI status for PR %s on %s status: %s" % (
                number, project, repr(context_successes)))
        if all(context_successes.values()):
            return 'success'
        return 'failure'

    def getChangesDependingOn(self, change, projects, tenant):
        """ Reverse lookup of PR depending on this one
        """
        # TODO(gitea) add dependencies to API
        #changes_dependencies = []
        #for cached_change_id, _change in self._change_cache.items():
        #    for dep_header in dependson.find_dependency_headers(
        #            _change.message):
        #        if change.url in dep_header:
        #            changes_dependencies.append(_change)
        #return changes_dependencies
        return []

    def mergePull(self, project: Project, number):
        api = giteapy.RepositoryApi(self.get_project_api_client(project))
        owner, repo = projectToOwnerAndName(project)
        #TODO are there any more params, message, etc needed?
        api.repo_merge_pull_request(owner, repo, number, body=giteapy.MergePullRequestOption(do="merge"))
        self.log.debug("Merged PR %s#%s", project, number)


class GiteaWebController(BaseWebController):

    log = logging.getLogger("zuul.GiteaWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    def _source_whitelisted(self, remote_ip, forwarded_ip):
        if remote_ip and remote_ip in self.connection.source_whitelist:
            return True
        if forwarded_ip and forwarded_ip in self.connection.source_whitelist:
            return True

    def _validate(self, body, token, request_signature):
        signature, _ = _sign_request(body, token)
        if not hmac.compare_digest(str(signature), str(request_signature)):
            self.log.info(
                "Missmatch (Payload Signature: %s, Request Signature: %s)" % (
                    signature, request_signature))
            return False
        return True

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-gitea-signature']
        except KeyError:
            raise cherrypy.HTTPError(
                401, 'x-gitea-signature header missing.')

        # TODO maybe retrieve dynamically from gitea api somehow
        token = self.connection.webhook_secret
        if not self._validate(body, token, request_signature):
            # Give a second attempt as a token could have been
            # re-generated server side. Refresh the token then retry.
            #self.log.info(
            #    "Refresh cached webhook token and re-check signature")
            #token = self.connection.get_project_webhook_token(
            #    project, force_refresh=True)
            #if not self._validate(body, token, request_signature):
            raise cherrypy.HTTPError(
                401,
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        # https://docs.gitea.io/en-us/webhooks/
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        if not self._source_whitelisted(
                getattr(cherrypy.request.remote, 'ip'),
                headers.get('x-forwarded-for')):
            self._validate_signature(body, headers)
        else:
            self.log.info(
                "Payload origin IP address whitelisted. Skip verify")

        json_payload = json.loads(body.decode('utf-8'))
        job = self.zuul_web.rpc.submitJob(
            'gitea:%s:payload' % self.connection.connection_name,
            {'event': headers.get('x-gitea-event'),'payload': json_payload})

        return json.loads(job.data[0])


def getSchema():
    gitea_connection = v.Any(str, v.Schema(dict))
    return gitea_connection
