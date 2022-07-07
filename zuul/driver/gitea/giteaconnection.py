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
import concurrent.futures
import hmac
import hashlib
import json
import time
import logging
import threading
import urllib

import cherrypy
import cachecontrol
from cachecontrol.cache import DictCache
from cachecontrol.heuristics import BaseHeuristic
import cachetools
import giteaclient

from zuul.connection import (
    BaseConnection, ZKChangeCacheMixin, ZKBranchCacheMixin
)
from zuul.web.handler import BaseWebController
from zuul.lib.logutil import get_annotated_logger
from zuul.model import Ref, Branch, Tag
from zuul.driver.gitea.giteamodel import PullRequest, GiteaTriggerEvent
from zuul.model import DequeueEvent
from zuul.zk.branch_cache import BranchCache
from zuul.zk.change_cache import (
    AbstractChangeCache,
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


class GiteaEventProcessor(object):
    def __init__(self, connector, event_tuple, connection_event):
        self.connector = connector
        self.connection = connector.connection
        self.ts, self.body, self.event_type, self.delivery = event_tuple
        logger = logging.getLogger("zuul.GiteaEventProcessor")
        self.zuul_event_id = self.delivery
        self.log = get_annotated_logger(logger, self.zuul_event_id)
        self.connection_event = connection_event
        # We typically return a list of one event, but we can return
        # multiple Zuul events from a single Github event.
        self.events = []

    def run(self):
        self.log.debug("Starting event processing")
        try:
            self._process_event()
        except Exception:
            self.log.exception("Exception when processing event:")
        finally:
            self.log.debug("Finished event processing")
        return self.events, self.connection_event

    def _process_event(self):
        if self.connector._stopped:
            return

        try:
            method = getattr(self, '_event_' + self.event_type)
        except AttributeError:
            # TODO(gtema): Gracefully handle event types we don't care about
            # instead of logging an exception.
            message = "Unhandled X-Giea-Event: {0}".format(self.event_type)
            self.log.debug(message)
            # Returns empty on unhandled events
            return

        self.log.debug("Handling %s event", self.event_type)
        events = []
        try:
            events = method()
            if not events:
                events = []
            elif not isinstance(events, list):
                events = [events]
        except Exception:
            # NOTE(gtema): We should report back to the PR we could
            # not process the event, to give the user a chance to
            # retrigger.
            self.log.exception('Exception when handling event:')

        for event in events:
            event.delivery = self.delivery
            event.zuul_event_id = self.delivery
            event.timestamp = self.ts
            project = self.connection.source.getProject(event.project_name)
            change = None
            if event.change_number:
                change_key = self.connection.source.getChangeKey(event)
                change = self.connection._getChange(change_key,
                                                    refresh=True,
                                                    event=event)
                self.log.debug("Refreshed change %s,%s",
                               event.change_number, event.patch_number)

            # If this event references a branch and we're excluding
            # unprotected branches, we might need to check whether the
            # branch is now protected.
            if hasattr(event, "branch") and event.branch:
                protected = None
                if change:
                    # PR based events already have the information if the
                    # target branch is protected so take the information
                    # from there.
                    protected = change.branch_protected
                self.connection.checkBranchCache(project.name, event,
                                                 protected=protected)

            event.project_hostname = self.connection.canonical_hostname
        self.events = events

    def _event_push(self):
        base_repo = self.body.get('repository')

        event = GiteaTriggerEvent()
        event.connection_name = self.connection.connection_name
        event.trigger_name = 'gitea'
        event.project_name = base_repo.get('full_name')
        event.type = 'push'

        event.ref = self.body.get('ref')
        event.oldrev = self.body.get('before')
        event.newrev = self.body.get('after')
        event.commits = self.body.get('commits')

        ref_parts = event.ref.split('/', 2)  # ie, ['refs', 'heads', 'foo/bar']

        if ref_parts[1] == "heads":
            # necessary for the scheduler to match against particular branches
            event.branch = ref_parts[2]

        self.connection.clearConnectionCacheOnBranchEvent(event)

        return event

    def _event_pull_request(self):
        action = self.body.get('action')
        pr_body = self.body.get('pull_request')

        event = self._pull_request_to_event(pr_body)
        event.account = self._get_sender(self.body)

        event.type = 'pull_request'
        if action == 'opened':
            event.action = 'opened'
        elif action == 'closed':
            event.action = 'closed'
        elif action == 'reopened':
            event.action = 'reopened'
        elif action == 'edited':
            event.action = 'edited'
            if 'body' in self.body.get('changes', {}):
                event.body_edited = True
        else:
            return None

        return event

    def _event_issue_comment(self):
        """Handles pull request comments"""
        action = self.body.get('action')
        if action != 'created':
            return
        if not self.body.get('issue', {}).get('pull_request'):
            # Do not process non-PR issue comment
            return
        pr_body = self._issue_to_pull_request(self.body)
        if pr_body is None:
            return

        event = self._pull_request_to_event(pr_body)
        event.account = self._get_sender(self.body)
        event.comment = self.body.get('comment').get('body')
        event.type = 'pull_request'
        event.action = 'comment'
        return event

    def _issue_to_pull_request(self, body):
        number = body.get('issue').get('number')
        project_name = body.get('repository').get('full_name')
        pr_body, pr_obj = self.connection.getPull(
            project_name, number, self.zuul_event_id)
        if pr_body is None:
            self.log.debug('Pull request #%s not found in project %s' %
                           (number, project_name))
        return pr_body

    def _pull_request_to_event(self, pr_body):
        event = GiteaTriggerEvent()
        event.connection_name = self.connection.connection_name
        event.trigger_name = 'gitea'

        base = pr_body.get('base')
        base_repo = base.get('repo')
        head = pr_body.get('head')

        event.project_name = base_repo.get('full_name')
        event.change_number = pr_body.get('number')
        event.change_url = self.connection.getPullUrl(event.project_name,
                                                      event.change_number)
        event.updated_at = pr_body.get('updated_at')
        event.branch = base.get('ref')
        event.ref = "refs/pull/" + str(pr_body.get('number')) + "/head"
        event.patch_number = head.get('sha')

        event.title = pr_body.get('title')

        return event

    def _get_sender(self, body):
        return body.get('sender').get('login')


class GiteaEventConnector:
    """Move events from Gitea into the scheduler"""

    log = logging.getLogger("zuul.GiteaEventConnector")

    def __init__(self, connection):
        self.connection = connection
        self.event_queue = connection.event_queue
        self._stopped = False
        self._events_in_progress = set()
        self._dispatcher_wake_event = threading.Event()
        self._event_dispatcher = threading.Thread(
            name='GiteaEventDispatcher', target=self.run_event_dispatcher,
            daemon=True)
        self._thread_pool = concurrent.futures.ThreadPoolExecutor()
        self._event_forward_queue = collections.deque()

    def stop(self):
        self._stopped = True
        self._dispatcher_wake_event.set()
        self.event_queue.election.cancel()
        self._event_dispatcher.join()

        self._thread_pool.shutdown()

    def start(self):
        self._event_dispatcher.start()

    def _onNewEvent(self):
        self._dispatcher_wake_event.set()
        # Stop the data watch in case the connector was stopped
        return not self._stopped

    def run_event_dispatcher(self):
        # Wait for the scheduler to prime its config so that we have
        # the full tenant list before we start moving events.
        self.connection.sched.primed_event.wait()
        if self._stopped:
            return
        self.event_queue.registerEventWatch(self._onNewEvent)
        # Set the wake event so we get an initial run
        self._dispatcher_wake_event.set()
        while not self._stopped:
            try:
                self.event_queue.election.run(self._dispatchEventsMain)
            except Exception:
                self.log.exception("Exception handling Gitea event:")
            # In case we caught an exception with events in progress,
            # reset these in case we run the loop again.
            self._events_in_progress = set()
            self._event_forward_queue = collections.deque()

    def _dispatchEventsMain(self):
        while True:
            # We can start processing events as long as we're running;
            # if we are stopping, then we need to continue this loop
            # until previously processed events are completed but not
            # start processing any new events.
            if self._dispatcher_wake_event.is_set() and not self._stopped:
                self._dispatcher_wake_event.clear()
                self._dispatchEvents()

            # Now process the futures from this or any previous
            # iterations of the loop.
            if len(self._event_forward_queue):
                self._forwardEvents()

            # If there are no futures, we can sleep until there are
            # new events (or stop altogether); otherwise we need to
            # continue processing futures.
            if not len(self._event_forward_queue):
                if self._stopped:
                    return
                self._dispatcher_wake_event.wait(10)
            else:
                # Sleep a small amount of time to give the futures
                # time to complete.
                self._dispatcher_wake_event.wait(0.1)

    def _dispatchEvents(self):
        # This is the first half of the event dispatcher.  It reads
        # events from the webhook event queue and passes them to a
        # concurrent executor for pre-processing.
        for event in self.event_queue:
            if self._stopped:
                break
            if event.ack_ref in self._events_in_progress:
                continue
            etuple = self._eventAsTuple(event)
            log = get_annotated_logger(self.log, etuple.delivery)
            log.debug("Gitea Webhook Received")
            log.debug("X-Gitea-Event: %s", etuple.event_type)
            processor = GiteaEventProcessor(self, etuple, event)
            future = self._thread_pool.submit(processor.run)

            # Events are acknowledged in the event forwarder loop after
            # pre-processing. This way we can ensure that no events are
            # lost.
            self._events_in_progress.add(event.ack_ref)
            self._event_forward_queue.append(future)

    def _forwardEvents(self):
        # This is the second half of the event dispatcher.  It
        # collects pre-processed events from the concurrent executor
        # and forwards them to the scheduler queues.
        while True:
            try:
                if not len(self._event_forward_queue):
                    return
                # Peek at the next event and see if it's done or if we
                # need to wait for the next loop iteration.
                if not self._event_forward_queue[0].done():
                    return
                future = self._event_forward_queue.popleft()
                events, connection_event = future.result()
                try:
                    for event in events:
                        self.connection.logEvent(event)
                        if isinstance(event, DequeueEvent):
                            self.connection.sched.addChangeManagementEvent(
                                event)
                        else:
                            self.connection.sched.addTriggerEvent(
                                self.connection.driver_name, event
                            )
                finally:
                    # Ack event in Zookeeper
                    self.event_queue.ack(connection_event)
                    self._events_in_progress.remove(connection_event.ack_ref)
            except Exception:
                self.log.exception("Exception moving Gitea event:")

    @staticmethod
    def _eventAsTuple(event):
        body = event.get("body")
        headers = event.get("headers", {})
        event_type = headers.get('x-gitea-event')
        delivery = headers.get('x-gitea-delivery')
        return EventTuple(time.time(), body, event_type, delivery)


class GiteaClientManager:
    log = logging.getLogger('zuul.GiteaConnection.GiteaClientManager')

    def __init__(self, connection_config):
        self.connection_config = connection_config
        self.baseurl = self.connection_config.get('baseurl')

        # ssl verification must default to true
        verify_ssl = self.connection_config.get('verify_ssl', 'true')
        self.verify_ssl = True
        if verify_ssl.lower() == 'false':
            self.verify_ssl = False

        # NOTE(jamielennox): Better here would be to cache to memcache or file
        # or something external - but zuul already sucks at restarting so in
        # memory probably doesn't make this much worse.

        # NOTE(tobiash): Unlike documented cachecontrol doesn't priorize
        # the etag caching but doesn't even re-request until max-age was
        # elapsed.
        #
        # Thus we need to add a custom caching heuristic which simply drops
        # the cache-control header containing max-age. This way we force
        # cachecontrol to only rely on the etag headers.
        #
        # http://cachecontrol.readthedocs.io/en/latest/etags.html
        # http://cachecontrol.readthedocs.io/en/latest/custom_heuristics.html
        class NoAgeHeuristic(BaseHeuristic):
            def update_headers(self, response):
                if 'cache-control' in response.headers:
                    del response.headers['cache-control']

        self.cache_adapter = cachecontrol.CacheControlAdapter(
            DictCache(),
            cache_etags=True,
            heuristic=NoAgeHeuristic())

        # Logging of rate limit is optional as this does additional requests
        rate_limit_logging = self.connection_config.get(
            'rate_limit_logging', 'true')
        self._log_rate_limit = True
        if rate_limit_logging.lower() == 'false':
            self._log_rate_limit = False

        self.app_id = None
        self.app_key = None
        self._initialized = False

        self._installation_map_lock = threading.Lock()
        self.installation_map = {}
        self.installation_token_cache = {}

        # The version of github enterprise stays None for github.com
        self._github_version = None

    def initialize(self):
        self.log.info('Authing to GitHub')
        self._authenticateGithubAPI()
        self._prime_installation_map()
        self._initialized = True

    @property
    def initialized(self):
        return self._initialized

    def getGiteaClient(
        self, project_name=None, zuul_event_id=None
    ):
        return None

    def getGiteaRepoClient(
        self, project_name=None, zuul_event_id=None
    ):
        return None


class GiteaConnection(ZKChangeCacheMixin, ZKBranchCacheMixin, BaseConnection):
    driver_name = 'gitea'
    log = logging.getLogger("zuul.connection.gitea")
    payload_path = 'payload'
    _event_connector_class = GiteaEventConnector

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
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname')
        if not self.canonical_hostname:
            r = urllib.parse.urlparse(self.baseurl)
            if r.hostname:
                self.canonical_hostname = r.hostname
            else:
                self.canonical_hostname = 'localhost'
        self.git_ssh_key = self.connection_config.get('sshkey')
        self.projects = {}
        self.source = driver.getSource(self)
        self.sched = None

        self._gitea_client_manager = GiteaClientManager(
            self.connection_config)
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
        self.gitea_event_connector = self._event_connector_class(self)
        self.gitea_event_connector.start()

    def _stop_event_connector(self):
        if self.gitea_event_connector:
            self.gitea_event_connector.stop()

    def getWebController(self, zuul_web):
        return GiteaWebController(zuul_web, self)

    def getEventQueue(self):
        return getattr(self, "event_queue", None)

    def validateWebConfig(self, config, connections):
        if 'webhook_token' not in self.connection_config:
            raise Exception(
                "webhook_token not found in config for connection %s" %
                self.connection_name)
        return True

    def getGiteaRepoClient(
        self, project_name=None, zuul_event_id=None
    ):
        return self._gitea_client_manager.getGiteaRepoClient(
            project_name=project_name, zuul_event_id=zuul_event_id)

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project

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
        # Note(tobiash): We force the pull request number to int centrally here
        # because it can originate from different sources (github event, manual
        # enqueue event) where some might just parse the string and forward it.
        number = int(change_key.stable_id)
        change = self._change_cache.get(change_key)
        if change and not refresh:
            return change
        project = self.source.getProject(change_key.project_name)
        if not change:
            if not event:
                self.log.error("Change %s not found in cache and no event",
                               change_key)
            change = PullRequest(project.name)
            change.project = project
            change.number = number
            change.patchset = change_key.revision

        # This can be called multi-threaded during gitea event
        # preprocessing. In order to avoid data races perform locking
        # by cached key. Try to acquire the lock non-blocking at first.
        # If the lock is already taken we're currently updating the very
        # same chnange right now and would likely get the same data again.
        lock = self._change_update_lock.setdefault(change_key,
                                                   threading.Lock())
        if lock.acquire(blocking=False):
            try:
                pull = self.getPull(change.project.name, change.number,
                                    event=event)

                def _update_change(c):
                    self._updateChange(c, event, pull)

                change = self._change_cache.updateChangeWithRetry(
                    change_key, change, _update_change)
            finally:
                # We need to remove the lock here again so we don't leak
                # them.
                del self._change_update_lock[change_key]
                lock.release()
        else:
            # We didn't get the lock so we don't need to update the same
            # change again, but to be correct we should at least wait until
            # the other thread is done updating the change.
            log = get_annotated_logger(self.log, event)
            log.debug("Change %s is currently being updated, "
                      "waiting for it to finish", change)
            with lock:
                log.debug('Finished updating change %s', change)
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
        if hasattr(event, 'commits'):
            change.files = self.getPushedFileNames(event)
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
        if hasattr(event, 'commits'):
            change.files = self.getPushedFileNames(event)
        try:
            self._change_cache.set(change_key, change)
        except ConcurrentUpdateError:
            change = self._change_cache.get(change_key)
        return change

    def _updateChange(self, change, event, pull):
        log = get_annotated_logger(self.log, event)
        log.info("Updating %s" % (change,))
        change.pr, pr_obj = pull
        change.is_current_patchset = (change.pr.get('head').get('sha') ==
                                      change.patchset)
        change.ref = "refs/pull/%s/head" % change.number
        change.branch = change.pr.get('base').get('ref')
        change.base_sha = change.pr.get('base').get('sha')
        change.commit_id = change.pr.get('head').get('sha')
        change.owner = change.pr.get('user').get('login')
        # Don't overwrite the files list. The change object is bound to a
        # specific revision and thus the changed files won't change. This is
        # important if we got the files later because of the 300 files limit.
        if not change.files:
            # TODO(gtema): gitea does not give nice list with files
            change.files = None
        change.title = change.pr.get('title')
        change.open = change.pr.get('state') == 'open'

        message = change.pr.get("body") or ""
        if change.title:
            if message:
                message = "{}\n\n{}".format(change.title, message)
            else:
                message = change.title
        change.message = message
        change.body_text = change.pr.get("body_text")

        # Note(tobiash): The updated_at timestamp is a moving target that is
        # not bound to the pull request 'version' we can solve that by just not
        # updating the timestamp if the pull request is updated in the cache.
        # This way the old pull request object retains its old timestamp and
        # the update check works.
        if not change.updated_at:
            change.updated_at = int(time.mktime(self._gitTimestampToDate(
                change.pr.get('updated_at'))))

        # Note: Gitea returns different urls for the pr:
        #  - url: this is the url meant for api use
        #  - html_url: this is the url meant for use in browser (this is what
        #              change.url means)
        change.url = change.pr.get('html_url')
        change.uris = [
            'https://%s/%s/pull/%s' % (
                self.server, change.project.name, change.number),
        ]

        return change

    def _gitTimestampToDate(self, timestamp):
        return time.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

    def getProjectBranches(self, project, tenant, min_ltime=-1):
        refs = self.lsRemote(project.name)
        branches = [ref[len('refs/heads/'):] for ref in
                    refs if ref.startswith('refs/heads/')]
        return branches

    def getGitUrl(self, project):
        if self.git_ssh_key:
            return 'ssh://git@%s/%s.git' % (self.server, project.name)

        return 'https://%s/%s' % (self.server, project.name)

    def getGitwebUrl(self, project, sha=None, tag=None):
        url = 'https://%s/%s' % (self.server, project)
        if tag is not None:
            url += '/releases/tag/%s' % tag
        elif sha is not None:
            url += '/commit/%s' % sha
        return url

    def getPullUrl(self, project, number):
        return '%s/pull/%s' % (self.getGitwebUrl(project), number)

    def getPull(self, project_name, number, event=None):
        log = get_annotated_logger(self.log, event)
        gitea_repo = self.getGiteaRepoClient(project_name, zuul_event_id=event)
        owner, proj = project_name.split('/')
        for retry in range(5):
            try:
                probj = gitea_repo.repo_get_pull_request(owner, proj, number)
                if probj is not None:
                    break
                self.log.warning("Pull request #%s of %s/%s returned None!" % (
                                 number, owner, proj))
            except giteaclient.rest.ApiException:
                self.log.warning(
                    "Failed to get pull request #%s of %s/%s; retrying" %
                    (number, owner, proj))
            time.sleep(1)
        else:
            raise Exception("Failed to get pull request #%s of %s/%s" % (
                number, owner, proj))
        pr = probj.to_dict()
        files = set()
        # Gitea does not return changed files in the PR object. We can only
        # get this information from all PR commits
        for c in gitea_repo.repo_get_pull_request_commits(
                owner, proj, number
        ):
            for f in c.files:
                files.add(f.filename)
        pr['files'] = files

        labels = [l['name'] for l in pr['labels']]
        pr['labels'] = labels

        self._sha_pr_cache.update(project_name, pr)

        log.debug('Got PR %s#%s', project_name, number)
        return (pr, probj)

    def getPushedFileNames(self, event):
        files = set()
        for c in event.commits:
            for f in c.get('added') + c.get('modified') + c.get('removed'):
                files.add(f)
        return list(files)


class GiteaWebController(BaseWebController):

    log = logging.getLogger("zuul.GiteaWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web
        self.event_queue = ConnectionEventQueue(
            self.zuul_web.zk_client,
            self.connection.connection_name
        )
        self.token = self.connection.connection_config.get('webhook_token')

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-gitea-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'X-Gitea-Signature header missing.')

        payload_signature = _sign_request(body, self.token)

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
    def payload(self):
        # Note(tobiash): We need to normalize the headers. Otherwise we will
        # have trouble to get them from the dict afterwards.
        # e.g.
        # GitHub: sent: X-GitHub-Event received: X-GitHub-Event
        # urllib: sent: X-GitHub-Event received: X-Github-Event
        #
        # We cannot easily solve this mismatch as every http processing lib
        # modifies the header casing in its own way and by specification http
        # headers are case insensitive so just lowercase all so we don't have
        # to take care later.
        # Note(corvus): Don't use cherrypy's json_in here so that we
        # can validate the signature.
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        self._validate_signature(body, headers)
        # We cannot send the raw body through zookeeper, so it's easy to just
        # encode it as json, after decoding it as utf-8
        json_body = json.loads(body.decode('utf-8'))

        data = {'headers': headers, 'body': json_body}
        self.event_queue.put(data)
        return data
