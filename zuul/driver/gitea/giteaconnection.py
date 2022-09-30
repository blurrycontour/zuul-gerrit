# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
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

import collections
import hmac
import hashlib
import json
import time
import logging
import requests
import threading
import urllib
import uuid
import re

import cherrypy
import cachetools

from opentelemetry import trace

from zuul.connection import (
    BaseConnection, ZKChangeCacheMixin, ZKBranchCacheMixin
)
from zuul.web.handler import BaseWebController
from zuul.lib.logutil import get_annotated_logger
from zuul.lib import tracing
from zuul.model import Ref, Branch, Tag
from zuul.exceptions import MergeFailure
from zuul.driver.gitea.giteamodel import PullRequest, GiteaTriggerEvent
from zuul.zk.branch_cache import BranchCache, BranchFlag, BranchInfo
from zuul.zk.change_cache import (
    AbstractChangeCache,
    ChangeKey,
    ConcurrentUpdateError,
)
from zuul.zk.event_queues import ConnectionEventQueue


EventTuple = collections.namedtuple(
    "EventTuple", ["timestamp", "body", "event_type", "delivery"]
)


def _sign_request(body, secret):
    signature = hmac.new(
        secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return signature


class GiteaChangeCache(AbstractChangeCache):
    log = logging.getLogger("zuul.driver.GiteaChangeCache")

    CHANGE_TYPE_MAP = {
        "Ref": Ref,
        "Tag": Tag,
        "Branch": Branch,
        "PullRequest": PullRequest,
    }


class GiteaShaCache(object):
    def __init__(self):
        self.projects = {}

    def update(self, project_name, pr):
        project_cache = self.projects.setdefault(
            project_name,
            # Cache up to 4k shas for each project
            # Note we cache the actual sha for a PR and the
            # merge_commit_sha so we make this fairly large.
            cachetools.LRUCache(4096)
        )
        sha = pr['head']['sha']
        number = pr['number']
        cached_prs = project_cache.setdefault(sha, set())
        cached_prs.add(number)
        merge_commit_sha = pr.get('merge_commit_sha')
        if merge_commit_sha:
            cached_prs = project_cache.setdefault(merge_commit_sha, set())
            cached_prs.add(number)

    def get(self, project_name, sha):
        project_cache = self.projects.get(project_name, {})
        cached_prs = project_cache.get(sha, set())
        return cached_prs


class GiteaEventConnector(threading.Thread):
    """Move events from Gitea into the scheduler"""

    # NOTE(gtema): all webhooks are currently not
    # documented. They are revese-engineered from the
    # source code and real gitea server.

    log = logging.getLogger("zuul.GiteaEventConnector")
    tracer = trace.get_tracer("zuul")

    def __init__(self, connection):
        super().__init__()
        self.daemon = True
        self.connection = connection
        self.event_queue = connection.event_queue
        self._stopped = False
        self._process_event = threading.Event()
        self.event_handler_mapping = {
            'push': self._event_push,
            'create': self._event_create,
            'delete': self._event_delete,
            'pull_request': self._event_pull_request,
            'pull_request_approved': self._event_pull_review,
            'pull_request_rejected': self._event_pull_review,
            'issue_comment': self._event_issue_comment,
        }

    def stop(self):
        self._stopped = True
        self._process_event.set()
        self.event_queue.election.cancel()

    def _onNewEvent(self):
        self._process_event.set()
        # Stop the data watch in case the connector was stopped
        return not self._stopped

    def run(self):
        # Wait for the scheduler to prime its config so that we have
        # the full tenant list before we start moving events.
        self.connection.sched.primed_event.wait()
        if self._stopped:
            return
        self.event_queue.registerEventWatch(self._onNewEvent)
        while not self._stopped:
            try:
                self.event_queue.election.run(self._run)
            except Exception:
                self.log.exception("Exception handling Gitea event:")

    def _run(self):
        while not self._stopped:
            for event in self.event_queue:
                event_span = tracing.restoreSpanContext(
                    event.get("span_context"))
                attributes = {"rel": "GiteaEvent"}
                link = trace.Link(event_span.get_span_context(),
                                  attributes=attributes)
                with self.tracer.start_as_current_span(
                        "GiteaEventProcessing", links=[link]):
                    try:
                        self._handleEvent(event)
                    finally:
                        self.event_queue.ack(event)
                if self._stopped:
                    return
            self._process_event.wait(10)
            self._process_event.clear()

    def _handleEvent(self, connection_event):
        if self._stopped:
            return

        self.log.debug('Received event:', connection_event)

        zuul_event_id = str(uuid.uuid4())
        log = get_annotated_logger(self.log, zuul_event_id)
        timestamp = time.time()
        headers = connection_event.get('headers', {})
        json_body = connection_event['payload']
        log.debug("Received payload: %s", json_body)

        event_type = headers.get('x-gitea-event')
        event_sub_type = headers.get('x-gitea-event-type')
        log.debug("Received event: %s", event_type)

        if event_type not in self.event_handler_mapping:
            message = "Unhandled Gitea event: %s" % event_type
            log.info(message)
            return

        if event_type in self.event_handler_mapping:
            log.info("Handling event: %s" % event_type)

        try:
            event = self.event_handler_mapping[event_type](
                json_body, event_sub_type)
        except Exception:
            log.exception(
                'Exception when handling event: %s' % event_type)
            event = None

        if event:
            event.zuul_event_id = zuul_event_id
            event.timestamp = timestamp
            event.project_hostname = self.connection.canonical_hostname
            change = None
            if event.change_number:
                change_key = self.connection.source.getChangeKey(event)
                change = self.connection._getChange(
                    change_key, refresh=True, event=event)

            # If this event references a branch and we're excluding
            # unprotected branches, we might need to check whether the
            # branch is now protected.
            if hasattr(event, "branch") and event.branch:
                protected = None
                if change:
                    protected = change.branch_protected
                self.connection.checkBranchCache(
                    event.project_name, event, protected=protected)

            self.connection.logEvent(event)
            self.connection.sched.addTriggerEvent(
                self.connection.driver_name, event
            )

    def _event_base(self, body):
        event = GiteaTriggerEvent()
        event.connection_name = self.connection.connection_name
        event.project_name = body['repository']['full_name']
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)

        return event

    def _event_push(self, body, event_sub_type=None):
        """ Handles push event """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        # NotifyNewPullRequest
        event = self._event_base(body)
        event.type = 'gt_push'
        event.branch = body['ref'].replace('refs/heads/', '')
        event.ref = body['ref']
        event.newrev = body['after']
        event.oldrev = body['before']
        event.type = 'gt_push'
        event.commits = body.get('commits')
        event.branch_updated = True

        return event

    def _event_pull_request(self, body, event_sub_type=None):
        """ Handles pull request opened event """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        # NotifyNewPullRequest
        event = self._event_base(body)
        event.type = 'gt_pull_request'

        pr_body = body['pull_request']
        base = pr_body.get('base')
        base_repo = base.get('repo')
        head = pr_body.get('head')

        event.title = pr_body.get('title')
        event.project_name = base_repo.get('full_name')
        event.change_number = pr_body.get('number')
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)
        event.updated_at = pr_body.get('updated_at')
        event.branch = base.get('ref')
        event.ref = "refs/pull/" + str(pr_body.get('number')) + "/head"
        event.patch_number = head.get('sha')
        event.url = pr_body.get('url')

        if body['action'] == 'synchronized':
            # "edited" is when title or body are changed
            # "synchronized" is raised when new commit added
            event.action = 'changed'
        elif body['action'] == 'edited':
            event.action = 'edited'
            if 'body' in body.get('changes', {}):
                event.message_edited = True
        else:
            event.action = body['action']

        event.labels = [l["name"] for l in body.get('labels', [])]

        return event

    def _event_pull_review(self, body, event_sub_type=None):
        """ Handles pull request review event """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        event = self._event_base(body)
        event.type = 'gt_pull_request_review'
        # NOTE: gitea does not currently emit event when review is dismissed
        event.action = 'submitted'

        pr_body = body['pull_request']
        base = pr_body.get('base')
        base_repo = base.get('repo')
        head = pr_body.get('head')

        event.title = pr_body.get('title')
        event.project_name = base_repo.get('full_name')
        event.change_number = pr_body.get('number')
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)
        event.updated_at = pr_body.get('updated_at')
        event.branch = base.get('ref')
        event.ref = "refs/pull/" + str(pr_body.get('number')) + "/head"
        event.patch_number = head.get('sha')
        event.url = pr_body.get('url')

        if event_sub_type == "pull_request_review_rejected":
            event.state = "request_changes"
        elif event_sub_type == "pull_request_review_approved":
            event.state = "approved"

        event.labels = [l["name"] for l in body.get('labels', [])]

        return event

    def _event_issue_comment(self, body, event_sub_type=None):
        """ Handles issue (pull request) comments """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        # NotifyNewPullRequest
        event = self._event_base(body)
        event.type = 'gt_pull_request'

        # Process PullRequest related comment
        if (
            event_sub_type == 'pull_request_comment'
            and body.get('is_pull')
            and body.get('action') == 'created'
        ):
            issue_body = body['issue']
            repo = body['repository']

            event.title = issue_body.get('title')
            event.project_name = repo.get('full_name')
            # Sounds weird, but issue nr == PR nr
            event.change_number = issue_body.get('number')
            event.change_url = self.connection.getPullUrl(event.project_name,
                                                          event.change_number)

            event.comment = body['comment'].get('body')
            event.action = 'comment'
            # Gitea does not report head sha in the comments webhook
            pr = self.connection.getPull(
                event.project_name, event.change_number)
            event.patch_number = pr['head']['sha']

            return event
        elif (
            event_sub_type == 'pull_request_comment'
            and body.get('action') == 'reviewed'
        ):
            # PR review comment
            event.type = 'gt_pull_request_review'
            # NOTE: gitea does not currently emit event when
            # review is dismissed
            event.action = 'submitted'
            event.state = 'comment'

            pr_body = body['pull_request']
            base = pr_body.get('base')
            base_repo = base.get('repo')
            head = pr_body.get('head')

            event.title = pr_body.get('title')
            event.project_name = base_repo.get('full_name')
            event.change_number = pr_body.get('number')
            event.change_url = self.connection.getPullUrl(event.project_name,
                                                          event.change_number)
            event.updated_at = pr_body.get('updated_at')
            event.branch = base.get('ref')
            event.ref = "refs/pull/" + str(pr_body.get('number')) + "/head"
            event.patch_number = head.get('sha')
            event.url = pr_body.get('url')

            event.comment = body['review'].get('content')

            return event

    def _event_create(self, body, event_sub_type=None):
        """ Handles create event """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        # NotifyCreate
        event = self._event_base(body)
        ref_type = body.get('ref_type')
        if ref_type == 'branch':
            event.type = 'gt_push'
            # Here ref is branch name
            # getChangeKey require ref to be set
            event.ref = f"refs/heads/{body['ref']}"
            event.branch = body['ref']
            event.oldrev = '0' * 40
            event.newrev = body['sha']

            self.connection.clearConnectionCacheOnBranchEvent(event)
            return event

    def _event_delete(self, body, event_sub_type=None):
        """ Handles delete event """
        # https://github.com/go-gitea/gitea/blob/main/modules/notification/webhook/webhook.go
        # NotifyDelete
        # NOTE(gtema): for now do nothing on deletion
        return None


class GiteaAPIClientException(Exception):
    pass


class GiteaAPIClient:
    log = logging.getLogger('zuul.GiteaConnection.GiteaAPIClient')
    # NOTE(gtema): We do not need python client since it
    # is usually outdated and returns objects instead of
    # dicts, what makes it harder to us in testing

    def __init__(self, baseurl, api_token, project=None):
        self.session = requests.Session()
        self.api_token = api_token
        self.base_url = '%s/api/v1/' % baseurl
        self.project = project
        self.headers = {'Authorization': 'token %s' % self.api_token}

    def _manage_error(self, data, code, url, verb):
        if code < 400:
            return
        else:
            if isinstance(data, dict) and 'message' in data:
                message = data['message']
            else:
                message = "Unable to %s on %s (code: %s) due to: %s" % (
                    verb, url, code, data
                )
            raise GiteaAPIClientException(message)

    def get(self, url, params=None):
        self.log.debug("Getting resource %s ..." % url)
        ret = self.session.get(url, headers=self.headers, params=params)
        self.log.debug("GET returned (code: %s): %s" % (
            ret.status_code, ret.text))
        return ret.json(), ret.status_code, ret.url, 'GET'

    def list(self, url, params=None):
        self.log.debug("Listing resource %s ..." % url)
        if not params:
            params = dict()
        total_count = 0
        fetched = 0
        page = 1
        while True:
            ret = self.session.get(
                url, headers=self.headers, params=params)
            self.log.debug("LIST returned (code: %s, page: %s): %s" % (
                ret.status_code, page, ret.text))
            self._manage_error({}, ret.status_code, ret.url, 'LIST')
            total_count = int(ret.headers.get('x-total-count', 0))
            try:
                data = ret.json()
            except requests.exceptions.JSONDecodeError:
                raise GiteaAPIClientException(
                    f"Unable to process list response for {url}. "
                    f"List type is expected"
                )

            if isinstance(data, list):
                for rec in data:
                    yield rec
                    fetched += 1
                # Do bit more then simple fetched == total_count due to
                # eventual bugs
                if fetched >= total_count or len(data) == 0:
                    return
                else:
                    page += 1
                    params['page'] = page
            else:
                raise GiteaAPIClientException(
                    f"Unable to process list response for {url}. "
                    f"List type is expected"
                )

    def post(self, url, params=None):
        self.log.info(
            "Posting on resource %s, params (%s) ..." % (url, params))
        ret = self.session.post(url, json=params, headers=self.headers)
        self.log.debug("POST returned (code: %s): %s" % (
            ret.status_code, ret.text))
        try:
            data = ret.json()
        except requests.exceptions.JSONDecodeError:
            data = ret.text
        return data, ret.status_code, ret.url, 'POST'

    def list_repo_branches(self):
        path = 'repos/%s/branches' % self.project
        resp = list(self.list(self.base_url + path))
        self.log.debug(f"Got branches {resp}")
        return resp

    def get_pr(self, number):
        path = 'repos/%s/pulls/%s' % (self.project, number)
        resp = self.get(self.base_url + path)
        self._manage_error(*resp)
        return resp[0]

    def comment_pull(self, number, message):
        params = {"body": message}
        path = 'repos/%s/issues/%s/comments' % (self.project, number)
        resp = self.post(self.base_url + path, params)
        self._manage_error(*resp)
        return resp[0]

    def set_commit_status(self, sha, state, url, description, context):
        params = {
            "state": state,
            "context": context,
            "description": description,
            "target_url": url
        }
        path = 'repos/%s/statuses/%s' % (self.project, sha)
        resp = self.post(self.base_url + path, params)
        self._manage_error(*resp)
        return resp[0]

    def get_repo_branch(self, branch):
        path = 'repos/%s/branches/%s' % (self.project, branch)
        resp = self.get(self.base_url + path)
        self._manage_error(*resp)
        return resp[0]

    def merge_pr(
        self, number, merge_title=None, merge_message=None,
        sha=None, method='merge'
    ):
        params = {
            "Do": method,
        }
        if merge_title:
            params["MergeTitleField"] = merge_title
        if merge_message:
            params["MergeMessageField"] = merge_message
        if sha:
            params["head_commit_id"] = sha
        path = 'repos/%s/pulls/%s/merge' % (self.project, number)
        resp = self.post(self.base_url + path, params)
        self._manage_error(*resp)
        return resp[0]

    def search_issues(self, **params):
        path = 'repos/issues/search'
        resp = list(self.list(self.base_url + path, params=params))
        return resp

    def list_pr_reviews(self, number):
        path = 'repos/%s/pulls/%s/reviews' % (self.project, number)
        resp = list(self.list(self.base_url + path))
        reviews = []
        for review in resp:
            if (
                review.get('state') == 'APPROVED'
                and review.get('official', False)
                and not review.get('stale', False)
                and not review.get('dismissed', False)
            ):
                reviews.append(review)
        return reviews

    def list_commit_statuses(self, sha, state=None):
        path = 'repos/%s/commits/%s/statuses' % (self.project, sha)
        params = dict()
        if state:
            params['state'] = 'state'
        resp = list(self.list(self.base_url + path))
        return resp


class GiteaConnection(ZKChangeCacheMixin, ZKBranchCacheMixin, BaseConnection):
    driver_name = 'gitea'
    log = logging.getLogger("zuul.connection.gitea")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(GiteaConnection, self).__init__(driver, connection_name,
                                              connection_config)
        self._change_update_lock = {}
        if 'server' not in self.connection_config:
            raise Exception('server is required for gitea connections in '
                            '%s' % self.connection_name)
        self.server = self.connection_config.get('server')
        self.baseurl = self.connection_config.get(
            'baseurl', 'https://%s' % self.server).rstrip('/')
        self.cloneurl = self.connection_config.get(
            'cloneurl', self.baseurl).rstrip('/')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname')
        if not self.canonical_hostname:
            r = urllib.parse.urlparse(self.baseurl)
            if r.hostname:
                self.canonical_hostname = r.hostname
            else:
                self.canonical_hostname = 'localhost'
        self.api_token = self.connection_config.get('api_token')
        self.verify_ssl = connection_config.get('verify_ssl', True)
        self.projects = {}
        self.source = driver.getSource(self)
        self.sched = None

        self._sha_pr_cache = GiteaShaCache()

    def toDict(self):
        d = super().toDict()
        d.update({
            "baseurl": self.baseurl,
            "canonical_hostname": self.canonical_hostname,
            "server": self.server,
        })
        return d

    def onLoad(self, zk_client, component_registry):
        self.log.info('Starting Gitea connection: %s', self.connection_name)

        # Set the project branch cache to read only if no scheduler is
        # provided to prevent fetching the branches from the connection.
        self.read_only = not self.sched

        self.log.debug('Creating Zookeeper branch cache')
        self._branch_cache = BranchCache(zk_client, self, component_registry)

        self.log.info('Creating Zookeeper event queue')
        self.event_queue = ConnectionEventQueue(
            zk_client, self.connection_name
        )

        # If the connection was not loaded by a scheduler, but by e.g.
        # zuul-web, we want to stop here.
        if not self.sched:
            return

        self.log.debug("Creating Zookeeper change cache")
        self._change_cache = GiteaChangeCache(zk_client, self)

        self.log.info('Starting event connector')
        self._start_event_connector()

    def onStop(self):
        # TODO(jeblair): remove this check which is here only so that
        # zuul-web can call connections.stop to shut down the sql
        # connection.
        if hasattr(self, 'gitea_event_connector'):
            self._stop_event_connector()

    def _start_event_connector(self):
        self.gitea_event_connector = GiteaEventConnector(self)
        self.gitea_event_connector.start()

    def _stop_event_connector(self):
        if self.gitea_event_connector:
            self.gitea_event_connector.stop()
            self.gitea_event_connector.join()

    def getWebController(self, zuul_web):
        return GiteaWebController(zuul_web, self)

    def validateWebConfig(self, config, connections):
        if 'webhook_secret' not in self.connection_config:
            raise Exception(
                "webhook_secret not found in config for connection %s" %
                self.connection_name)
        return True

    def get_project_api_client(
        self, project_name=None
    ):
        self.log.debug("Building project %s api_client" % project_name)
        client = GiteaAPIClient(self.baseurl, self.api_token, project_name)
        return client

    def getProject(self, name):
        self.log.info("add project %s", name)
        return self.projects.get(name)

    def addProject(self, project):
        self.log.info("add project %s", project)
        self.projects[project.name] = project

    def _getProjectBranchesRequiredFlags(
            self, exclude_unprotected, exclude_locked):
        required_flags = BranchFlag.CLEAR
        if exclude_unprotected:
            self.log.info("here am i")
            required_flags |= BranchFlag.PROTECTED
        if not required_flags:
            self.log.info("here am i2")
            required_flags = BranchFlag.PRESENT
        return required_flags

    def _filterProjectBranches(
            self, branch_infos, exclude_unprotected, exclude_locked):
        if exclude_unprotected:
            branch_infos = [b for b in branch_infos if b.protected is True]
        return branch_infos

    def _fetchProjectBranches(self, project, required_flags):
        valid_flags = BranchFlag.PRESENT
        self.log.debug(
            f"Fetching project {project} branches "
            f"with required_flags={required_flags}"
        )
        gitea = self.get_project_api_client(project.name)
        branch_infos = [BranchInfo(
            x['name'],
            present=True,
            protected=x.get('protected', False))
            for x in gitea.list_repo_branches()]
        if BranchFlag.PROTECTED in required_flags:
            valid_flags |= BranchFlag.PROTECTED
            result = filter(lambda x: x.protected, branch_infos)
        else:
            result = branch_infos
        self.log.info("Got branches for %s: %s" % (project.name, result))
        return valid_flags, result

    def isBranchProtected(
        self, project_name, branch_name, zuul_event_id=None
    ):
        gitea = self.get_project_api_client(project_name)
        branch = gitea.get_repo_branch(branch_name)
        return branch.get('protected', False)

    def getChange(self, change_key, refresh=False, event=None):
        if change_key.connection_name != self.connection_name:
            return None
        if change_key.change_type == 'PullRequest':
            return self._getChange(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Tag':
            return self._getTag(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Branch':
            return self._getBranch(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Ref':
            return self._getRef(change_key, refresh=refresh, event=event)

    def _getChange(self, change_key, refresh=False, event=None):
        log = get_annotated_logger(self.log, event)
        number = int(change_key.stable_id)
        change = self._change_cache.get(change_key)
        if change and not refresh:
            log.debug("Getting change from cache %s" % str(change_key))
            return change
        project = self.source.getProject(change_key.project_name)
        url = None
        if not change:
            if not event:
                self.log.error("Change %s not found in cache and no event",
                               change_key)
            if event:
                url = event.change_url

            change = PullRequest(project.name)
            change.project = project
            change.number = number
            # patchset is the tips commit of the PR
            change.patchset = change_key.revision
            change.url = url or self.getPullUrl(project.name, number)

        log.debug("Getting change pr#%s from repository %s" % (
            number, project.name))
        log.info("Updating change from gitea %s" % change)
        pull = self.getPull(change.project.name, change.number)

        def _update_change(c):
            self._updateChange(c, event, pull)

        change = self._change_cache.updateChangeWithRetry(change_key, change,
                                                          _update_change)
        return change

    def _getTag(self, change_key, refresh=False, event=None):
        tag = change_key.stable_id
        change = self._change_cache.get(change_key)
        if change:
            if refresh:
                self._change_cache.updateChangeWithRetry(
                    change_key, change, lambda c: None)
            return change
        if not event:
            self.log.error("Change %s not found in cache and no event",
                           change_key)
        project = self.source.getProject(change_key.project_name)
        change = Tag(project)
        change.tag = tag
        change.ref = f'refs/tags/{tag}'
        change.oldrev = change_key.oldrev
        change.newrev = change_key.newrev
        # Build the url pointing to this tag/release on Gitea.
        change.url = self.getGitwebUrl(project, sha=change.newrev, tag=tag)
        # Gitea does not send changed files in the events.
        # Explicitly set files to None and let the pipelines processor
        # call the merger asynchronuously
        change.files = None
        if hasattr(event, 'commits'):
            change.files = self.getPushedFileNames(event)
        try:
            self._change_cache.set(change_key, change)
        except ConcurrentUpdateError:
            change = self._change_cache.get(change_key)
        return change

    def _getBranch(self, change_key, refresh=False, event=None):
        branch = change_key.stable_id
        change = self._change_cache.get(change_key)
        if change:
            if refresh:
                self._change_cache.updateChangeWithRetry(
                    change_key, change, lambda c: None)
            return change
        if not event:
            self.log.error("Change %s not found in cache and no event",
                           change_key)
        project = self.source.getProject(change_key.project_name)
        change = Branch(project)
        change.branch = branch
        change.ref = f'refs/heads/{branch}'
        change.oldrev = change_key.oldrev
        change.newrev = change_key.newrev
        change.url = self.getGitwebUrl(project, sha=change.newrev)
        # Gitea does not send changed files in the events.
        # Explicitly set files to None and let the pipelines processor
        # call the merger asynchronuously
        change.files = None
        try:
            self._change_cache.set(change_key, change)
        except ConcurrentUpdateError:
            change = self._change_cache.get(change_key)
        return change

    def _getRef(self, change_key, refresh=False, event=None):
        change = self._change_cache.get(change_key)
        if change:
            if refresh:
                self._change_cache.updateChangeWithRetry(
                    change_key, change, lambda c: None)
            return change
        if not event:
            self.log.error("Change %s not found in cache and no event",
                           change_key)
        project = self.source.getProject(change_key.project_name)
        change = Ref(project)
        change.ref = change_key.stable_id
        change.oldrev = change_key.oldrev
        change.newrev = change_key.newrev
        change.url = self.getGitwebUrl(project, sha=change.newrev)
        # Gitea does not send changed files in the events.
        # Explicitly set files to None and let the pipelines processor
        # call the merger asynchronuously
        try:
            self._change_cache.set(change_key, change)
        except ConcurrentUpdateError:
            change = self._change_cache.get(change_key)
        return change

    def _updateChange(self, change, event, pull):
        log = get_annotated_logger(self.log, event)
        log.info("Updating %s" % (change,))
        change.pr = pull
        change.ref = "refs/pull/%s/head" % change.number
        change.branch = change.pr.get('base').get('ref')
        change.is_current_patchset = (change.pr.get('head').get('sha') ==
                                      change.patchset)
        change.base_sha = change.pr.get('base').get('sha')
        change.commit_id = change.pr.get('head').get('sha')
        change.patchset = change.pr.get('head').get('sha')
        change.owner = change.pr.get('user').get('login')
        change.title = change.pr.get('title')
        change.open = change.pr.get('state') == 'open'

        # Never change the is_merged attribute back to unmerged. This is
        # crucial so this cannot race with mergePull wich sets this attribute
        # after a successful merge.
        if not change.is_merged:
            change.is_merged = change.pr.get('merged')

        message = change.pr.get("body") or ""
        if change.title:
            if message:
                message = "{}\n\n{}".format(change.title, message)
            else:
                message = change.title
        change.message = message
        change.updated_at = change.pr.get('updated_at')
        change.can_merge = change.pr.get('mergeable')
        # Files changes are not part of the Pull Request data
        change.files = None
        change.url = change.pr.get('html_url')
        change.uris = [change.url]
        change.labels = change.pr.get('labels')

        # Gather data for mergeability checks
        self._updateCanMergeInfo(change, event)
        return change

    def _updateCanMergeInfo(self, change, event):
        # NOTE: Gitea has ``mergeable`` attribute, but similarly to GitHub
        # driver it can not be used for checking branch protection rules.
        # We need to recalculate some bits on our side.
        gitea = self.get_project_api_client(change.project)
        if change.title.lower().startswith("wip"):
            change.draft = True
        branch_info = gitea.get_repo_branch(change.branch)
        if (
            not (change.can_merge and branch_info.get('user_can_merge', False))
        ):
            change.can_merge = False
            self.log.info(
                f"Change {change} can not merge because "
                f"zuul is not allowed to.")
        change.branch_protected = branch_info.get('protected', False)
        change.required_status_check = branch_info.get(
            'enable_status_check', False)
        change.required_contexts = set(
            branch_info.get('status_check_contexts', []) or [])
        change.required_approvals = int(
            branch_info.get('required_approvals', 0))
        change.reviews = gitea.list_pr_reviews(change.number)
        change.contexts = set([x.get('context') for x in
                               gitea.list_commit_statuses(
                                   change.patchset, state='success')])

        if (
            len(change.reviews) >= change.required_approvals
        ):
            self.log.debug("Change is approved")
            change.approved = True

    def _gitTimestampToDate(self, timestamp):
        return time.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

    def getGitUrl(self, project):
        cloneurl = '%s/%s.git' % (self.cloneurl, project.name)
        if (cloneurl.startswith('http') and self.api_token != '' and
            not re.match("http?://.+:.+@.+", cloneurl)):
            cloneurl = '%s://%s:%s@%s/%s.git' % (
                self.cloneurl.split('://')[0],
                'git',
                self.api_token,
                self.cloneurl.split('://')[1],
                project.name)
        return cloneurl

    def getGitwebUrl(self, project, sha=None, tag=None):
        url = 'https://%s/%s' % (self.server, project)
        if tag is not None:
            url += '/releases/tag/%s' % tag
        elif sha is not None:
            url += '/commit/%s' % sha
        return url

    def getPullUrl(self, project, number):
        return '%s/pulls/%s' % (self.getGitwebUrl(project), number)

    def getPull(self, project_name, number, event=None):
        log = get_annotated_logger(self.log, event=event)
        gitea = self.get_project_api_client(project_name)
        pr = gitea.get_pr(number)
        # Normalize labels
        pr['labels'] = [l['name'] for l in pr.get('labels', [])]
        log.info('Got PR %s#%s', project_name, number)
        return pr

    def commentPull(self, project, number, message):
        gitea = self.get_project_api_client(project)
        gitea.comment_pull(number, message)
        self.log.info("Commented on PR %s#%s", project, number)

    def setCommitStatus(self, project, sha, state, url='',
                        description='', context=''):
        gitea = self.get_project_api_client(project)
        gitea.set_commit_status(
            sha, state, url, description, context)
        self.log.info("Set commit CI flag status : %s" % description)
        # Wait for 1 second as flag timestamp is by second
        time.sleep(1)

    def canMerge(self, change, allow_needs, event=None, allow_refresh=False):
        log = get_annotated_logger(self.log, event)

        if allow_refresh:
            self._updateCanMergeInfo(change, event)

        can_merge = True
        if change.draft:
            can_merge = False
        if not change.can_merge:
            can_merge = False

        if change.branch_protected:
            # NOTE: it does not make much sense to reimplement complete
            # branch protection rules analysis on Zuul side. For now
            # only look whether at least enough approvals are given.
            if (
                change.required_approvals > 0
                and len(change.reviews) < change.required_approvals
            ):
                log.debug(
                    f"Change {change} can not merge because "
                    f"it is not approved")
                can_merge = False

            if change.required_status_check:
                if (
                    change.required_contexts
                    and change.required_contexts - change.contexts
                ):
                    can_merge = False
                if len(change.contexts) == 0:
                    can_merge = False
                log.debug(
                    f"Change {change} can not merge because "
                    f"it is not having required checks")

        return can_merge

    def mergePull(self, project, number,
                  merge_title=None, merge_message=None, sha=None,
                  method='merge', zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        gitea = self.get_project_api_client(project)
        try:
            gitea.merge_pr(
                number, merge_title=merge_title, merge_message=merge_message,
                sha=sha, method=method)
            log.debug("Merged PR %s#%s", project, number)
        except GiteaAPIClientException as e:
            raise MergeFailure(e)
        log.debug("Merged PR %s#%s", project, number)

    def getChangesDependingOn(self, change, projects, tenant):
        changes = []
        if not change.uris:
            return changes
        if not projects:
            # We aren't in the context of a change queue and we just
            # need to query all installations of this tenant. This currently
            # only happens if certain features of the zuul trigger are
            # used; generally it should be avoided.
            projects = [p for p in tenant.all_projects
                        if p.connection_name == self.connection_name]
        # Otherwise we use the input projects list and look for changes in the
        # supplied projects.
        gitea = self.get_project_api_client(None)
        keys = set()
        # TODO: Max of 5 OR operators can be used per query and
        # query can be max of 256 characters long
        # If making changes to this pattern you may need to update
        # tests/fakegitea.py
        pattern = ' OR '.join(['"Depends-On: %s"' % x for x in change.uris])
        params = dict(
            q=pattern,
            type='pulls',
            state='open'
        )
        # Repeat the search for each client (project)
        for pr in gitea.search_issues(**params):
            proj = pr['repository'].get('full_name')
            num = pr['number']
            sha = None
            # This is not a ChangeKey
            key = (proj, num, sha)
            # A single tenant could have multiple projects with the same
            # name on different sources. Ensure we use the canonical name
            # to handle that case.
            s_project = self.source.getProject(proj)
            trusted, t_project = tenant.getProject(
                s_project.canonical_name)
            # ignore projects zuul doesn't know about
            if not t_project:
                continue
            if key in keys:
                continue
            self.log.debug("Found PR %s/%s needs %s/%s" %
                           (proj, num, change.project.name,
                            change.number))
            keys.add(key)
        self.log.debug("Ran search issues: %s", params)
        for key in keys:
            (proj, num, sha) = key
            dep_change_key = ChangeKey(self.connection_name, proj,
                                       'PullRequest', str(num), str(sha))
            try:
                change = self._getChange(dep_change_key)
                changes.append(change)
            except Exception:
                self.log.warning(
                    f"Change {key} is having Depends-On, "
                    f"but can not be fetched. Ignoring.")
        return changes


class GiteaWebController(BaseWebController):

    log = logging.getLogger("zuul.GiteaWebController")
    tracer = trace.get_tracer("zuul")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web
        self.event_queue = ConnectionEventQueue(
            self.zuul_web.zk_client,
            self.connection.connection_name
        )
        self.webhook_secret = self.connection.connection_config.get(
            'webhook_secret')

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-gitea-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'X-Gitea-Signature header missing.')

        payload_signature = _sign_request(body, self.webhook_secret)

        self.log.debug("Payload Signature: {0}".format(str(payload_signature)))
        self.log.debug("Request Signature: {0}".format(str(request_signature)))
        if not hmac.compare_digest(
            str(payload_signature), str(request_signature)):
            raise cherrypy.HTTPError(
                401,
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

        return True

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    @tracer.start_as_current_span("GiteaEvent")
    def payload(self):
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        self._validate_signature(body, headers)
        self.log.info("Event header: %s" % headers)
        self.log.info("Event body: %s" % body)
        # We cannot send the raw body through zookeeper, so it's easy to just
        # encode it as json, after decoding it as utf-8
        json_payload = json.loads(body.decode('utf-8'))

        data = {
            'headers': headers,
            'payload': json_payload,
            'span_context': tracing.getSpanContext(trace.get_current_span()),
        }
        self.event_queue.put(data)
        return data
