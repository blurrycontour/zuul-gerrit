# Copyright 2011 OpenStack, LLC.
# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2023-2024 Acme Gating, LLC
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
import copy
import datetime
import enum
import itertools
import json
import logging
import paramiko
import pprint
import re
import re2
import requests
import shlex
import threading
import time
import urllib
import urllib.parse

from typing import Dict, List
from uuid import uuid4

from opentelemetry import trace

from zuul import version as zuul_version
from zuul.connection import (
    BaseConnection, ZKChangeCacheMixin, ZKBranchCacheMixin
)
from zuul.driver.gerrit.auth import FormAuth
from zuul.driver.gerrit.gcloudauth import GCloudAuth
from zuul.driver.gerrit.gerritmodel import GerritChange, GerritTriggerEvent
from zuul.driver.gerrit.gerriteventssh import GerritSSHEventListener
from zuul.driver.gerrit.gerriteventchecks import GerritChecksPoller
from zuul.driver.gerrit.gerriteventkafka import GerritKafkaEventListener
from zuul.driver.gerrit.gerriteventawskinesis import (
    GerritAWSKinesisEventListener,
)
from zuul.driver.gerrit.gerriteventgcloudpubsub import (
    GerritGcloudPubsubEventListener,
)
from zuul.driver.git.gitwatcher import GitWatcher
from zuul.lib import tracing
from zuul.lib.logutil import get_annotated_logger
from zuul.model import Ref, Tag, Branch, Project
from zuul.zk.branch_cache import BranchCache, BranchFlag, BranchInfo
from zuul.zk.change_cache import (
    AbstractChangeCache,
    ChangeKey,
    ConcurrentUpdateError,
)
from zuul.zk.event_queues import ConnectionEventQueue

# HTTP timeout in seconds
TIMEOUT = 30
# SSH connection timeout
SSH_TIMEOUT = TIMEOUT

# commentSizeLimit default set by Gerrit.  Gerrit is a bit
# vague about what this means, it says
#
#  Comments which exceed this size will be rejected ... Size
#  computation is approximate and may be off by roughly 1% ...
#  Default is 16k
#
# This magic number is int((16 << 10) * 0.98).  Robot comments
# are accounted for separately.
GERRIT_HUMAN_MESSAGE_LIMIT = 16056


class HTTPConflictException(Exception):
    message = "Received response 409"


class HTTPBadRequestException(Exception):
    pass


class GerritEventProcessingException(Exception):
    pass


class GerritChangeCache(AbstractChangeCache):
    log = logging.getLogger("zuul.driver.GerritChangeCache")

    CHANGE_TYPE_MAP = {
        "Ref": Ref,
        "Tag": Tag,
        "Branch": Branch,
        "GerritChange": GerritChange,
    }


class GerritChangeData(object):
    """Compatability layer for SSH/HTTP

    This class holds the raw data returned from a change query over
    SSH or HTTP.  Most of the work of parsing the data and storing it
    on the change is in the gerritmodel.GerritChange class, however
    this does perform a small amount of parsing of dependencies since
    they are handled outside of that class.  This provides an API to
    that data independent of the source.

    """

    SSH = 1
    HTTP = 2

    def __init__(self, fmt, data, related=None, files=None,
                 zuul_query_ltime=None):
        self.format = fmt
        self.data = data
        self.files = files
        self.zuul_query_ltime = zuul_query_ltime

        if fmt == self.SSH:
            self.parseSSH(data)
        else:
            self.parseHTTP(data)
            if related:
                self.parseRelatedHTTP(data, related)

    def parseSSH(self, data):
        self.needed_by = []
        self.depends_on = None
        self.message = data['commitMessage']
        self.current_patchset = str(data['currentPatchSet']['number'])
        self.number = str(data['number'])
        self.id = data['id']

        if 'dependsOn' in data:
            parts = data['dependsOn'][0]['ref'].split('/')
            self.depends_on = (parts[3], parts[4])

        for needed in data.get('neededBy', []):
            parts = needed['ref'].split('/')
            self.needed_by.append((parts[3], parts[4]))

    def parseHTTP(self, data):
        rev = data['revisions'][data['current_revision']]
        self.message = rev['commit']['message']
        self.current_patchset = str(rev['_number'])
        self.number = str(data['_number'])
        self.id = data['change_id']

    def parseRelatedHTTP(self, data, related):
        self.needed_by = []
        self.depends_on = None
        current_rev = data['revisions'][data['current_revision']]
        for change in related['changes']:
            for parent in current_rev['commit']['parents']:
                if change['commit']['commit'] == parent['commit']:
                    self.depends_on = (change['_change_number'],
                                       change['_revision_number'])
                    break
            else:
                self.needed_by.append((change['_change_number'],
                                       change['_revision_number']))


class QueryHistory:
    class Query(enum.Enum):
        SEEN = 1  # Not a real query, just that we've seen the change
        CHANGE = 2  # The main change query

    def __init__(self):
        self.queries = collections.defaultdict(lambda: dict())

    def getByKey(self, query, change_key):
        if not isinstance(change_key, ChangeKey):
            raise Exception("Must supply a ChangeKey")
        key = (change_key.stable_id, change_key.revision)
        return self.queries[query].get(key)

    def add(self, query, change):
        if not isinstance(change, GerritChange):
            raise Exception("Must supply a GerritChange")
        key = (change.number, change.patchset)
        self.queries[query][key] = change


class GerritEventConnector(threading.Thread):
    """Move events from Gerrit to the scheduler."""

    IGNORED_EVENTS = (
        'cache-eviction',  # evict-cache plugin
        'fetch-ref-replicated',
        'fetch-ref-replication-scheduled',
        'ref-replicated',
        'ref-replication-scheduled',
        'ref-replication-done'
    )

    log = logging.getLogger("zuul.GerritEventConnector")
    tracer = trace.get_tracer("zuul")
    delay = 10.0

    def __init__(self, connection):
        super(GerritEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self.event_queue = connection.event_queue
        self._stopped = False
        self._connector_wake_event = threading.Event()

    def stop(self):
        self._stopped = True
        self._connector_wake_event.set()
        self.event_queue.election.cancel()

    def _onNewEvent(self):
        self._connector_wake_event.set()
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
                self.log.exception("Exception moving Gerrit event:")
                time.sleep(1)

    def _run(self):
        self.log.info("Won connection event queue election for %s",
                      self.connection.connection_name)
        while not self._stopped and self.event_queue.election.is_still_valid():
            qlen = len(self.event_queue)
            if qlen:
                self.log.debug("Connection event queue length for %s: %s",
                               self.connection.connection_name, qlen)
            for event in self.event_queue:
                event_span = tracing.restoreSpanContext(
                    event.get("span_context"))
                attributes = {"rel": "GerritEvent"}
                link = trace.Link(event_span.get_span_context(),
                                  attributes=attributes)
                with self.tracer.start_as_current_span(
                        "GerritEventProcessing", links=[link]):
                    try:
                        self._handleEvent(event)
                    except GerritEventProcessingException as e:
                        self.log.warning("Skipping event due to %s", e)
                    finally:
                        self.event_queue.ack(event)
                if self._stopped:
                    return
            self._connector_wake_event.wait(10)
            self._connector_wake_event.clear()
        self.log.info("Terminating connection event queue processing for %s",
                      self.connection.connection_name)

    def _handleEvent(self, connection_event):
        timestamp = connection_event["timestamp"]
        data = connection_event["payload"]
        if "zuul_event_id" in connection_event:
            zuul_event_id = connection_event["zuul_event_id"]
        else:
            # TODO: This is for backwards compat; Remove after 7.0.0
            zuul_event_id = str(uuid4().hex)

        log = get_annotated_logger(self.log, zuul_event_id)
        now = time.time()
        delay = max((timestamp + self.delay) - now, 0.0)
        # Gerrit can produce inconsistent data immediately after an
        # event, So ensure that we do not deliver the event to Zuul
        # until at least a certain amount of time has passed.  Note
        # that if we receive several events in succession, we will
        # only need to delay for the first event.  In essence, Zuul
        # should always be a constant number of seconds behind Gerrit.

        log.debug("Handling event received %ss ago, delaying %ss",
                  now - timestamp, delay)
        time.sleep(delay)
        event = GerritTriggerEvent()
        event.timestamp = timestamp
        event.connection_name = self.connection.connection_name
        event.zuul_event_id = zuul_event_id

        event.type = data.get('type')
        event.uuid = data.get('uuid')

        # This catches when a change is merged, as it could potentially
        # have merged layout info which will need to be read in.
        # Ideally this would be done with a refupdate event so as to catch
        # directly pushed things as well as full changes being merged.
        # But we do not yet get files changed data for pure refupdate events.
        # TODO(jlk): handle refupdated events instead of just changes
        if event.type == 'change-merged':
            event.branch_updated = True
        event.trigger_name = 'gerrit'
        change = data.get('change')
        event.project_hostname = self.connection.canonical_hostname
        if change:
            event.project_name = change.get('project')
            event.branch = change.get('branch')
            event.change_number = str(change.get('number'))
            event.change_url = change.get('url')
            patchset = data.get('patchSet')
            if patchset:
                event.patch_number = str(patchset.get('number'))
                event.ref = patchset.get('ref')
            event.approvals = data.get('approvals', [])
            event.comment = data.get('comment')
            patchsetcomments = data.get('patchSetComments', {}).get(
                "/PATCHSET_LEVEL")
            if patchsetcomments:
                event.patchsetcomments = []
                for patchsetcomment in patchsetcomments:
                    event.patchsetcomments.append(
                        patchsetcomment.get('message'))
            event.added = data.get('added')
            event.removed = data.get('removed')
        refupdate = data.get('refUpdate')
        if refupdate:
            event.project_name = refupdate.get('project')
            event.ref = refupdate.get('refName')
            event.oldrev = refupdate.get('oldRev')
            event.newrev = refupdate.get('newRev')
        if event.project_name is None:
            # ref-replica* events
            event.project_name = data.get('project')
        if event.type == 'project-created':
            event.project_name = data.get('projectName')
        if event.type == 'project-head-updated':
            event.project_name = data.get('projectName')
            event.ref = data.get('newHead')
            event.branch = event.ref[len('refs/heads/'):]
            event.default_branch_changed = True
            self.log.debug('Updating default branch for %s to %s',
                           event.project_name, event.branch)
            self.connection._branch_cache.setProjectDefaultBranch(
                event.project_name, event.branch)
        # Map the event types to a field name holding a Gerrit
        # account attribute. See Gerrit stream-event documentation
        # in cmd-stream-events.html
        accountfield_from_type = {
            'patchset-created': 'uploader',
            'draft-published': 'uploader',  # Gerrit 2.5/2.6
            'change-abandoned': 'abandoner',
            'change-restored': 'restorer',
            'change-merged': 'submitter',
            'merge-failed': 'submitter',  # Gerrit 2.5/2.6
            'comment-added': 'author',
            'ref-updated': 'submitter',
            'reviewer-added': 'reviewer',  # Gerrit 2.5/2.6
            'topic-changed': 'changer',
            'hashtags-changed': 'editor',
            'vote-deleted': 'deleter',
            'project-created': None,  # Gerrit 2.14
            'pending-check': None,  # Gerrit 3.0+
            'project-head-updated': None,
        }
        event.account = None
        if event.type in accountfield_from_type:
            field = accountfield_from_type[event.type]
            if field:
                event.account = data.get(accountfield_from_type[event.type])
        else:
            log.warning("Received unrecognized event type '%s' "
                        "from Gerrit. Can not get account information." %
                        (event.type,))

        # This checks whether the event created or deleted a branch so
        # that Zuul may know to perform a reconfiguration on the
        # project.
        branch_refs = 'refs/heads/'
        if (event.type == 'ref-updated' and
            ((not event.ref.startswith('refs/')) or
             event.ref.startswith(branch_refs))):

            if event.ref.startswith(branch_refs):
                event.branch = event.ref[len(branch_refs):]
            else:
                event.branch = event.ref

            self.connection.clearConnectionCacheOnBranchEvent(event)

        change = self._getChange(event, connection_event.zuul_event_ltime)
        if (change and change.patchset and
            event.change_number and event.patch_number is None):
            event.patch_number = str(change.patchset)
        self.connection.logEvent(event)
        self.connection.sched.addTriggerEvent(
            self.connection.driver_name, event
        )

    def _getChange(self, event, connection_event_ltime):
        # Grab the change if we are managing the project or if it exists in the
        # cache as it may be a dependency
        change = None
        if event.change_number:
            refresh = True
            change_key = self.connection.source.getChangeKey(event)
            change = self.connection._change_cache.get(change_key)
            if change is None:
                refresh = False
                for tenant in self.connection.sched.abide.tenants.values():
                    # TODO(fungi): it would be better to have some simple means
                    # of inferring the hostname from the connection, or at
                    # least split this into separate method arguments, rather
                    # than assembling and passing in a baked string.
                    if (None, None) != tenant.getProject('/'.join((
                            self.connection.canonical_hostname,
                            event.project_name))):
                        refresh = True
                        break
            else:
                # We have a cache entry for this change Get the
                # query ltime for the cache entry; if it's after the
                # event ltime, we don't need to refresh.
                if (change.zuul_query_ltime and
                    change.zuul_query_ltime > connection_event_ltime):
                    refresh = False

            if refresh:
                # Call _getChange for the side effect of updating the
                # cache.  Note that this modifies Change objects outside
                # the main thread.
                # NOTE(jhesketh): Ideally we'd just remove the change from the
                # cache to denote that it needs updating. However the change
                # object is already used by Items and hence BuildSets etc. and
                # we need to update those objects by reference so that they
                # have the correct/new information and also avoid hitting
                # gerrit multiple times.
                change = self.connection._getChange(
                    change_key, refresh=True, event=event,
                    allow_key_update=True)
        return change


class GerritConnection(ZKChangeCacheMixin, ZKBranchCacheMixin, BaseConnection):
    driver_name = 'gerrit'
    log = logging.getLogger("zuul.GerritConnection")
    tracer = trace.get_tracer("zuul")
    iolog = logging.getLogger("zuul.GerritConnection.io")
    depends_on_re = re.compile(r"^Depends-On: (I[0-9a-f]{40})\s*$",
                               re.MULTILINE | re.IGNORECASE)
    refname_bad_sequences = re2.compile(
        r"[ \\*\[?:^~\x00-\x1F\x7F]|"  # Forbidden characters
        r"@{|\.\.|\.$|^@$|/$|^/|//+")  # everything else we can check with re2
    replication_timeout = 300
    replication_retry_interval = 5
    _poller_class = GerritChecksPoller
    _ref_watcher_class = GitWatcher
    ref_watcher_poll_interval = 60
    submit_retry_backoff = 10

    EVENT_SOURCE_NONE = 'none'
    EVENT_SOURCE_STREAM_EVENTS = 'stream-events'
    EVENT_SOURCE_KAFKA = 'kafka'
    EVENT_SOURCE_KINESIS = 'kinesis'
    EVENT_SOURCE_GCLOUD_PUBSUB = 'gcloudpubsub'

    def __init__(self, driver, connection_name, connection_config):
        super(GerritConnection, self).__init__(driver, connection_name,
                                               connection_config)
        if 'server' not in self.connection_config:
            raise Exception('server is required for gerrit connections in '
                            '%s' % self.connection_name)
        if 'user' not in self.connection_config:
            raise Exception('user is required for gerrit connections in '
                            '%s' % self.connection_name)

        self.user = self.connection_config.get('user')
        self.server = self.connection_config.get('server')
        self.ssh_server = self.connection_config.get('ssh_server', self.server)
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.port = int(self.connection_config.get('port', 29418))
        self.keyfile = self.connection_config.get('sshkey', None)
        self.keepalive = int(self.connection_config.get('keepalive', 60))
        self.max_dependencies = self.connection_config.get(
            'max_dependencies', None)
        if self.max_dependencies is not None:
            self.max_dependencies = int(self.max_dependencies)
        self.event_source = self.EVENT_SOURCE_NONE
        # TODO(corvus): Document this when the checks api is stable;
        # it's not useful without it.
        enable_stream_events = self.connection_config.get(
            'stream_events', True)
        if enable_stream_events in [
                'true', 'True', '1', 1, 'TRUE', True]:
            self.event_source = self.EVENT_SOURCE_STREAM_EVENTS
        if self.connection_config.get('kafka_bootstrap_servers', None):
            self.event_source = self.EVENT_SOURCE_KAFKA
        elif self.connection_config.get('aws_kinesis_region', None):
            self.event_source = self.EVENT_SOURCE_KINESIS
        elif self.connection_config.get('gcloud_pubsub_project', None):
            self.event_source = self.EVENT_SOURCE_GCLOUD_PUBSUB

        # Thread for whatever event source we use
        self.event_thread = None
        # Next two are only used by checks plugin
        self.poller_thread = None
        self.ref_watcher_thread = None
        self.client = None
        self.watched_checkers = []
        self.project_checker_map = {}
        self.version = (0, 0, 0)
        self.submit_whole_topic = None
        self.ssh_timeout = SSH_TIMEOUT

        self.baseurl = self.connection_config.get(
            'baseurl', 'https://%s' % self.server).rstrip('/')
        default_gitweb_url_template = '{baseurl}/gitweb?' \
                                      'p={project.name}.git;' \
                                      'a=commitdiff;h={sha}'
        url_template = self.connection_config.get('gitweb_url_template',
                                                  default_gitweb_url_template)
        self.gitweb_url_template = url_template

        self.projects = {}
        self.gerrit_event_connector = None
        self.source = driver.getSource(self)

        self.session = None
        self.password = self.connection_config.get('password', None)
        self.git_over_ssh = self.connection_config.get('git_over_ssh', False)
        self.auth_type = self.connection_config.get('auth_type', None)
        self.anonymous_git = False
        if self.password or self.auth_type == 'gcloud_service':
            self.verify_ssl = self.connection_config.get('verify_ssl', True)
            if self.verify_ssl not in ['true', 'True', '1', 1, 'TRUE']:
                self.verify_ssl = False
            self.user_agent = 'Zuul/%s %s' % (
                zuul_version.release_string,
                requests.utils.default_user_agent())
            self.session = requests.Session()
            if self.auth_type == 'digest':
                authclass = requests.auth.HTTPDigestAuth
            elif self.auth_type == 'form':
                authclass = FormAuth
            elif self.auth_type == 'gcloud_service':
                authclass = GCloudAuth
                # The executors in google cloud may not have access
                # to the gerrit account credentials, so just use
                # anonymous http access for git
                self.anonymous_git = True
            else:
                authclass = requests.auth.HTTPBasicAuth
            self.auth = authclass(self.user, self.password)

    def setWatchedCheckers(self, checkers_to_watch):
        self.log.debug("Setting watched checkers to %s", checkers_to_watch)
        self.watched_checkers = set()
        self.project_checker_map = {}
        schemes_to_watch = set()
        uuids_to_watch = set()
        for x in checkers_to_watch:
            if 'scheme' in x:
                schemes_to_watch.add(x['scheme'])
            if 'uuid' in x:
                uuids_to_watch.add(x['uuid'])
        if schemes_to_watch:
            # get a list of all configured checkers
            try:
                configured_checkers = self.get('plugins/checks/checkers/')
            except Exception:
                self.log.exception("Unable to get checkers")
                configured_checkers = []

            # filter it through scheme matches in checkers_to_watch
            for checker in configured_checkers:
                if checker['status'] != 'ENABLED':
                    continue
                checker_scheme, checker_id = checker['uuid'].split(':')
                repo = checker['repository']
                repo = self.canonical_hostname + '/' + repo
                # map scheme matches to project names
                if checker_scheme in schemes_to_watch:
                    repo_checkers = self.project_checker_map.setdefault(
                        repo, set())
                    repo_checkers.add(checker['uuid'])
                    self.watched_checkers.add(checker['uuid'])
        # add uuids from checkers_to_watch
        for x in uuids_to_watch:
            self.watched_checkers.add(x)

    def toDict(self):
        d = super().toDict()
        d.update({
            "baseurl": self.baseurl,
            "canonical_hostname": self.canonical_hostname,
            "server": self.server,
            "ssh_server": self.ssh_server,
            "port": self.port,
        })
        return d

    def url(self, path):
        return self.baseurl + '/a/' + path

    def get(self, path):
        url = self.url(path)
        self.log.debug('GET: %s' % (url,))
        r = self.session.get(
            url,
            verify=self.verify_ssl,
            auth=self.auth, timeout=TIMEOUT,
            headers={'User-Agent': self.user_agent})
        self.iolog.debug('Received: %s %s' % (r.status_code, r.text,))
        if r.status_code == 409:
            raise HTTPConflictException()
        elif r.status_code != 200:
            raise Exception("Received response %s" % (r.status_code,))
        ret = None
        if r.text and len(r.text) > 4:
            try:
                ret = json.loads(r.text[4:])
            except Exception:
                self.log.exception(
                    "Unable to parse result %s from post to %s" %
                    (r.text, url))
                raise
        return ret

    def post(self, path, data):
        url = self.url(path)
        self.log.debug('POST: %s' % (url,))
        self.log.debug('data: %s' % (data,))
        r = self.session.post(
            url, data=json.dumps(data).encode('utf8'),
            verify=self.verify_ssl,
            auth=self.auth, timeout=TIMEOUT,
            headers={'Content-Type': 'application/json;charset=UTF-8',
                     'User-Agent': self.user_agent})
        self.iolog.debug('Received: %s %s' % (r.status_code, r.text,))
        if r.status_code == 409:
            raise HTTPConflictException()
        if r.status_code == 400:
            raise HTTPBadRequestException('Received response 400: %s' % r.text)
        elif r.status_code != 200:
            raise Exception("Received response %s: %s" % (
                r.status_code, r.text))
        ret = None
        if r.text and len(r.text) > 4:
            try:
                ret = json.loads(r.text[4:])
            except Exception:
                self.log.exception(
                    "Unable to parse result %s from post to %s" %
                    (r.text, url))
                raise
        return ret

    def getProject(self, name: str) -> Project:
        return self.projects.get(name)

    def addProject(self, project: Project) -> None:
        self.projects[project.name] = project

    def getChange(self, change_key, refresh=False, event=None):
        if change_key.connection_name != self.connection_name:
            return None
        if change_key.change_type == 'GerritChange':
            return self._getChange(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Tag':
            return self._getTag(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Branch':
            return self._getBranch(change_key, refresh=refresh, event=event)
        elif change_key.change_type == 'Ref':
            return self._getRef(change_key, refresh=refresh, event=event)

    def _checkMaxDependencies(self, change, history):
        if change and history:
            history.add(history.Query.SEEN, change)
            if (self.max_dependencies is not None and
                len(history.queries[history.Query.SEEN]) >
                self.max_dependencies):
                raise GerritEventProcessingException(
                    f"Change {change} has too many dependencies")

    def _getChange(self, change_key, refresh=False, history=None,
                   event=None, allow_key_update=False):
        # Ensure number and patchset are str
        change = self._change_cache.get(change_key)
        self._checkMaxDependencies(change, history)
        if change and not refresh:
            return change
        if not change:
            if not event:
                self.log.error("Change %s not found in cache and no event",
                               change_key)
            change = GerritChange(None)
            change.number = change_key.stable_id
            change.patchset = change_key.revision
        self._checkMaxDependencies(change, history)
        return self._updateChange(change_key, change, event, history,
                                  allow_key_update)

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
        change.url = self._getWebUrl(project, sha=change.newrev)
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
        change.url = self._getWebUrl(project, sha=change.newrev)
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
        change.url = self._getWebUrl(project, sha=change.newrev)
        try:
            self._change_cache.set(change_key, change)
        except ConcurrentUpdateError:
            change = self._change_cache.get(change_key)
        return change

    def _getDependsOnFromCommit(self, message, change, event):
        log = get_annotated_logger(self.log, event)
        records = []
        seen = set()
        for match in self.depends_on_re.findall(message):
            if match in seen:
                log.debug("Ignoring duplicate Depends-On: %s", match)
                continue
            seen.add(match)
            query = "change:%s" % (match,)
            log.debug("Updating %s: Running query %s to find needed changes",
                      change, query)
            records.extend(self.simpleQuery(query, event=event))
        return [(x.number, x.current_patchset) for x in records]

    def _getNeededByFromCommit(self, change_id, change, event):
        log = get_annotated_logger(self.log, event)
        records = []
        seen = set()
        query = 'message:{%s}' % change_id
        log.debug("Updating %s: Running query %s to find changes needed-by",
                  change, query)
        results = self.simpleQuery(query, event=event)
        for result in results:
            for match in self.depends_on_re.findall(
                    result.message):
                if match != change_id:
                    continue
                # Note: This is not a ChangeCache ChangeKey
                key = (result.number, result.current_patchset)
                if key in seen:
                    continue
                log.debug("Updating %s: Found change %s,%s "
                          "needs %s from commit",
                          change, key[0], key[1], change_id)
                seen.add(key)
                records.append(result)
        return [(x.number, x.current_patchset) for x in records]

    def _updateChange(self, key, change, event, history,
                      allow_key_update=False):
        log = get_annotated_logger(self.log, event)

        # In case this change is already in the history we have a
        # cyclic dependency and don't need to update ourselves again
        # as this gets done in a previous frame of the call stack.
        # NOTE(jeblair): The only case where this can still be hit is
        # when we get an event for a change with no associated
        # patchset; for instance, when the gerrit topic is changed.
        # In that case, we will update change 1234,None, which will be
        # inserted into the cache as its own entry, but then we will
        # resolve the patchset before adding it to the history list,
        # then if there are dependencies, we can walk down and then
        # back up to the version of this change with a patchset which
        # will match the history list but will have bypassed the
        # change cache because the previous object had a patchset of
        # None.  All paths hit the change cache first.  To be able to
        # drop history, we need to resolve the patchset on events with
        # no patchsets before adding the entry to the change cache.
        if history and change.number and change.patchset:
            history_change = history.getByKey(history.Query.CHANGE, key)
            if history_change:
                log.debug("Change %s is in history", change)
                return history_change

        log.info("Updating %s", change)
        data = self.queryChange(change.number, event=event)

        # Do a local update without updating the cache so that we can
        # reference this change when we recurse for dependencies.
        change.update(data, {}, self)

        # Get the dependencies for this change, and recursively update
        # dependent changes (recursively calling this method).
        if not change.is_merged:
            extra = self._updateChangeDependencies(
                log, key, change, data, event, history)
        else:
            extra = {}

        # Actually update this change in the change cache.
        def _update_change(c):
            return c.update(data, extra, self)

        change = self._change_cache.updateChangeWithRetry(
            key, change, _update_change, allow_key_update=allow_key_update)

        return change

    def _updateChangeDependencies(self, log, key, change, data, event,
                                  history):
        if history is None:
            history = QueryHistory()
        history.add(history.Query.CHANGE, change)

        needs_changes = set()
        git_needs_changes = []
        if data.depends_on is not None:
            dep_num, dep_ps = data.depends_on
            log.debug("Updating %s: Getting git-dependent change %s,%s",
                      change, dep_num, dep_ps)
            dep_key = ChangeKey(self.connection_name, None,
                                'GerritChange', str(dep_num), str(dep_ps))
            dep = self._getChange(dep_key, history=history,
                                  event=event)
            # This is a git commit dependency. So we only ignore it if it is
            # already merged. So even if it is "ABANDONED", we should not
            # ignore it.
            if (not dep.is_merged) and dep not in needs_changes:
                git_needs_changes.append(dep_key.reference)
                needs_changes.add(dep_key.reference)

        compat_needs_changes = []
        for (dep_num, dep_ps) in self._getDependsOnFromCommit(
                data.message, change, event):
            log.debug("Updating %s: Getting commit-dependent "
                      "change %s,%s", change, dep_num, dep_ps)
            dep_key = ChangeKey(self.connection_name, None,
                                'GerritChange', str(dep_num), str(dep_ps))
            dep = self._getChange(dep_key, history=history,
                                  event=event)
            if dep.open and dep not in needs_changes:
                compat_needs_changes.append(dep_key.reference)
                needs_changes.add(dep_key.reference)

        needed_by_changes = set()
        git_needed_by_changes = []
        for (dep_num, dep_ps) in data.needed_by:
            try:
                log.debug("Updating %s: Getting git-needed change %s,%s",
                          change, dep_num, dep_ps)
                dep_key = ChangeKey(self.connection_name, None,
                                    'GerritChange', str(dep_num), str(dep_ps))
                dep = self._getChange(dep_key, history=history,
                                      event=event)
                if (dep.open and dep.is_current_patchset and
                    dep not in needed_by_changes):
                    git_needed_by_changes.append(dep_key.reference)
                    needed_by_changes.add(dep_key.reference)
            except GerritEventProcessingException:
                raise
            except Exception:
                log.exception("Failed to get git-needed change %s,%s",
                              dep_num, dep_ps)

        compat_needed_by_changes = []
        for (dep_num, dep_ps) in self._getNeededByFromCommit(
                data.id, change, event):
            try:
                log.debug("Updating %s: Getting commit-needed change %s,%s",
                          change, dep_num, dep_ps)
                # Because a commit needed-by may be a cross-repo
                # dependency, cause that change to refresh so that it will
                # reference the latest patchset of its Depends-On (this
                # change). In case the dep is already in history we already
                # refreshed this change so refresh is not needed in this case.
                dep_key = ChangeKey(self.connection_name, None,
                                    'GerritChange', str(dep_num), str(dep_ps))
                refresh = not history.getByKey(history.Query.CHANGE, dep_key)
                dep = self._getChange(
                    dep_key, refresh=refresh, history=history,
                    event=event)
                if (dep.open and dep.is_current_patchset
                    and dep not in needed_by_changes):
                    compat_needed_by_changes.append(dep_key.reference)
                    needed_by_changes.add(dep_key.reference)
            except GerritEventProcessingException:
                raise
            except Exception:
                log.exception("Failed to get commit-needed change %s,%s",
                              dep_num, dep_ps)

        return dict(
            git_needs_changes=git_needs_changes,
            compat_needs_changes=compat_needs_changes,
            git_needed_by_changes=git_needed_by_changes,
            compat_needed_by_changes=compat_needed_by_changes,
        )

    def isMerged(self, change, head=None):
        self.log.debug("Checking if change %s is merged" % change)
        if not change.number:
            self.log.debug("Change has no number; considering it merged")
            # Good question.  It's probably ref-updated, which, ah,
            # means it's merged.
            return True

        data = self.queryChange(change.number)
        key = ChangeKey(self.connection_name, None,
                        'GerritChange', str(change.number),
                        str(change.patchset))

        def _update_change(c):
            c.update(data, {}, self)

        self._change_cache.updateChangeWithRetry(key, change, _update_change)

        if change.is_merged:
            self.log.debug("Change %s is merged" % (change,))
        else:
            self.log.debug("Change %s is not merged" % (change,))
        if not head:
            return change.is_merged
        if not change.is_merged:
            return False

        ref = 'refs/heads/' + change.branch
        self.log.debug("Waiting for %s to appear in git repo" % (change))
        if not hasattr(change, '_ref_sha'):
            self.log.error("Unable to confirm change %s in git repo: "
                           "the change has not been reported; "
                           "this pipeline may be misconfigured "
                           "(check for multiple Gerrit connections)." %
                           (change,))
            return False

        if self._waitForRefSha(change.project, ref, change._ref_sha):
            self.log.debug("Change %s is in the git repo" %
                           (change))
            return True
        self.log.debug("Change %s did not appear in the git repo" %
                       (change))
        return False

    def _waitForRefSha(self, project: Project,
                       ref: str, old_sha: str='') -> bool:
        # Wait for the ref to show up in the repo
        start = time.time()
        while time.time() - start < self.replication_timeout:
            sha = self.getRefSha(project, ref)
            if old_sha != sha:
                return True
            time.sleep(self.replication_retry_interval)
        return False

    def getRefSha(self, project: Project, ref: str) -> str:
        refs = {}  # type: Dict[str, str]
        try:
            refs = self.getInfoRefs(project)
        except Exception:
            self.log.exception("Exception looking for ref %s" %
                               ref)
        sha = refs.get(ref, '')
        return sha

    def canMerge(self, change, allow_needs, event=None):
        log = get_annotated_logger(self.log, event)
        if not change.number:
            log.debug("Change has no number; considering it merged")
            # Good question.  It's probably ref-updated, which, ah,
            # means it's merged.
            return True
        if change.wip:
            return False
        missing_labels = change.missing_labels - set(allow_needs)
        if missing_labels:
            self.log.debug("Unable to merge due to "
                           "missing labels: %s", missing_labels)
            return False
        for sr in change.submit_requirements:
            if sr.get('status') == 'UNSATISFIED':
                # Otherwise, we don't care and should skip.

                # We're going to look at each unsatisfied submit
                # requirement, and if one of the involved labels is an
                # "allow_needs" label, we will assume that Zuul may be
                # able to take an action which can cause the
                # requirement to be satisfied, and we will ignore it.
                # Otherwise, it is likely a requirement that Zuul can
                # not alter in which case the requirement should stand
                # and block merging.
                result = sr.get("submittability_expression_result", {})
                expression = result.get("expression", '')
                expr_contains_allow = False
                for allow in allow_needs:
                    if f'label:{allow}' in expression:
                        expr_contains_allow = True
                        break
                if not expr_contains_allow:
                    self.log.debug("Unable to merge due to "
                                   "submit requirement: %s", sr)
                    return False
        return True

    def getProjectOpenChanges(self, project: Project) -> List[GerritChange]:
        # This is a best-effort function in case Gerrit is unable to return
        # a particular change.  It happens.
        query = "project:{%s} status:open" % (project.name,)
        self.log.debug("Running query %s to get project open changes" %
                       (query,))
        data = self.simpleQuery(query)
        changes = []  # type: List[GerritChange]
        for record in data:
            try:
                change_key = ChangeKey(self.connection_name, None,
                                       'GerritChange',
                                       str(record.number),
                                       str(record.current_patchset))
                changes.append(self._getChange(change_key))
            except Exception:
                self.log.exception("Unable to query change %s",
                                   record.number)
        return changes

    @staticmethod
    def _checkRefFormat(refname: str) -> bool:
        # These are the requirements for valid ref names as per
        # man git-check-ref-format
        parts = refname.split('/')
        return \
            (GerritConnection.refname_bad_sequences.search(refname) is None and
             len(parts) > 1 and
             not any(part.startswith('.') or part.endswith('.lock')
                     for part in parts))

    def _getProjectBranchesRequiredFlags(
            self, exclude_unprotected, exclude_locked):
        return BranchFlag.PRESENT

    def _filterProjectBranches(
            self, branch_infos, exclude_unprotected, exclude_locked):
        return branch_infos

    def _fetchProjectBranches(self, project, required_flags):
        refs = self.getInfoRefs(project)
        heads = [str(k[len('refs/heads/'):]) for k in refs
                 if k.startswith('refs/heads/') and
                 GerritConnection._checkRefFormat(k)]
        branch_infos = [BranchInfo(h, present=True) for h in heads]
        return BranchFlag.PRESENT, branch_infos

    def _fetchProjectDefaultBranch(self, project):
        if not self.session:
            return 'master'
        head = None
        try:
            head = self.get(
                'projects/%s/HEAD' % (
                    urllib.parse.quote(project.name, safe=''),
                ))
            if head.startswith('refs/heads/'):
                head = head[len('refs/heads/'):]
        except Exception:
            self.log.exception("Unable to get HEAD")
        return head

    def isBranchProtected(self, project_name, branch_name,
                          zuul_event_id=None):
        # TODO: This could potentially be expanded to do something
        # with user-specific branches.
        return True

    def addEvent(self, data):
        # NOTE(mnaser): Certain plugins fire events which end up causing
        #               an unrecognized event log *and* a traceback if they
        #               do not contain full project information, we skip them
        #               here to keep logs clean.
        if data.get('type') in GerritEventConnector.IGNORED_EVENTS:
            return
        # Due to notedb, an high percentage of all events Zuul
        # processes are ref-updated of the /meta ref, and that is
        # unlikely to be used in Zuul.  Skip those here so that we
        # reduce traffic on the event queue.
        if data.get('type') == 'ref-updated':
            refname = data.get('refUpdate', {}).get('refName', '')
            if (refname.startswith('refs/changes/') and
                refname.endswith('/meta')):
                return

        event_uuid = uuid4().hex
        attributes = {
            "zuul_event_id": event_uuid,
        }
        # Gerrit events don't have an event id that could be used to globally
        # identify this event in the system so we have to generate one.
        with self.tracer.start_span(
                "GerritEvent", attributes=attributes) as span:
            event = {
                "timestamp": time.time(),
                "zuul_event_id": event_uuid,
                "span_context": tracing.getSpanContext(span),
                "payload": data,
            }
            self.event_queue.put(event)

    def review(self, item, change, message, submit, labels, checks_api,
               file_comments, phase1, phase2, zuul_event_id=None):
        if self.session:
            meth = self.review_http
        else:
            meth = self.review_ssh
        return meth(item, change, message, submit, labels, checks_api,
                    file_comments, phase1, phase2,
                    zuul_event_id=zuul_event_id)

    def review_ssh(self, item, change, message, submit, labels, checks_api,
                   file_comments, phase1, phase2, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        if checks_api:
            log.error("Zuul is configured to report to the checks API, "
                      "but no HTTP password is present for the connection "
                      "in the configuration file.")
        project = change.project.name
        cmd = 'gerrit review --project %s' % project
        if phase1:
            if message:
                b_len = len(message.encode('utf-8'))
                if b_len >= GERRIT_HUMAN_MESSAGE_LIMIT:
                    log.info("Message truncated %d > %d" %
                             (b_len, GERRIT_HUMAN_MESSAGE_LIMIT))
                    message = ("%s... (truncated)" %
                               message[:GERRIT_HUMAN_MESSAGE_LIMIT - 20])
                cmd += ' --message %s' % shlex.quote(message)
            for key, val in labels.items():
                if val is True:
                    cmd += ' --%s' % key
                else:
                    cmd += ' --label %s=%s' % (key, val)
            if self.version >= (2, 13, 0):
                cmd += ' --tag autogenerated:zuul:%s' % (item.pipeline.name)
        if phase2 and submit:
            cmd += ' --submit'
        changeid = '%s,%s' % (change.number, change.patchset)
        cmd += ' %s' % changeid
        out, err = self._ssh(cmd, zuul_event_id=zuul_event_id)
        return err

    def report_checks(self, log, item, change, changeid, checkinfo):
        checkinfo = checkinfo.copy()
        uuid = checkinfo.pop('uuid', None)
        scheme = checkinfo.pop('scheme', None)
        if uuid is None:
            uuids = self.project_checker_map.get(
                change.project.canonical_name, set())
            for u in uuids:
                if u.split(':')[0] == scheme:
                    uuid = u
                    break
        if uuid is None:
            log.error("Unable to find matching checker for %s %s",
                      item, checkinfo)
            return

        def fmt(t):
            return str(datetime.datetime.fromtimestamp(t))

        if item.enqueue_time:
            checkinfo['started'] = fmt(item.enqueue_time)
            if item.report_time:
                checkinfo['finished'] = fmt(item.report_time)
            url = item.formatItemUrl()
            if url:
                checkinfo['url'] = url
        if checkinfo:
            for x in range(1, 4):
                try:
                    self.post('changes/%s/revisions/%s/checks/%s' %
                              (changeid, change.commit, uuid),
                              checkinfo)
                    break
                except HTTPConflictException:
                    log.exception("Conflict submitting check data to gerrit.")
                    break
                except HTTPBadRequestException:
                    log.exception(
                        "Bad request submitting check data to gerrit.")
                    break
                except Exception as e:
                    log.exception("Error submitting check data to gerrit on "
                                  "attempt %s: %s", x, e)
                    time.sleep(x * self.submit_retry_backoff)

    def review_http(self, item, change, message, submit, labels,
                    checks_api, file_comments, phase1, phase2,
                    zuul_event_id=None):
        changeid = "%s~%s~%s" % (
            urllib.parse.quote(str(change.project), safe=''),
            urllib.parse.quote(str(change.branch), safe=''),
            change.id)
        log = get_annotated_logger(self.log, zuul_event_id)
        b_len = len(message.encode('utf-8'))
        if b_len >= GERRIT_HUMAN_MESSAGE_LIMIT:
            log.info("Message truncated %d > %d" %
                     (b_len, GERRIT_HUMAN_MESSAGE_LIMIT))
            message = ("%s... (truncated)" %
                       message[:GERRIT_HUMAN_MESSAGE_LIMIT - 20])
        data = dict(strict_labels=False)
        if phase1:
            data['message'] = message
            if change.is_current_patchset:
                if labels:
                    data['labels'] = labels
                if file_comments:
                    if self.version >= (2, 15, 0):
                        file_comments = copy.deepcopy(file_comments)
                        url = item.formatItemUrl()
                        for comments in itertools.chain(
                                file_comments.values()):
                            for comment in comments:
                                comment['robot_id'] = 'zuul'
                                comment['robot_run_id'] = \
                                    item.current_build_set.uuid
                                if url:
                                    comment['url'] = url
                        data['robot_comments'] = file_comments
                    else:
                        data['comments'] = file_comments
            if self.version >= (2, 13, 0):
                data['tag'] = 'autogenerated:zuul:%s' % (item.pipeline.name)
            if checks_api:
                self.report_checks(log, item, change, changeid, checks_api)
            if (message or data.get('labels') or data.get('comments')
                or data.get('robot_comments')):
                for x in range(1, 4):
                    try:
                        self.post('changes/%s/revisions/%s/review' %
                                  (changeid, change.commit),
                                  data)
                        break
                    except HTTPConflictException:
                        log.exception("Conflict submitting data to gerrit.")
                        break
                    except HTTPBadRequestException:
                        log.exception(
                            "Bad request submitting check data to gerrit.")
                        break
                    except Exception as e:
                        log.exception(
                            "Error submitting data to gerrit "
                            "on attempt %s: %s",
                            x, e)
                        time.sleep(x * self.submit_retry_backoff)
        if phase2 and change.is_current_patchset and submit:
            for x in range(1, 4):
                try:
                    self.post('changes/%s/submit' % (changeid,), {})
                    break
                except HTTPConflictException:
                    log.info("Conflict submitting data to gerrit, "
                             "change may already be merged")
                    break
                except HTTPBadRequestException:
                    log.exception(
                        "Bad request submitting check data to gerrit.")
                    break
                except Exception as e:
                    log.exception(
                        "Error submitting data to gerrit on attempt %s: %s",
                        x, e)
                    time.sleep(x * self.submit_retry_backoff)

    def queryChangeSSH(self, number, event=None):
        args = '--all-approvals --comments --commit-message'
        args += ' --current-patch-set --dependencies --files'
        args += ' --patch-sets --submit-records'
        cmd = 'gerrit query --format json %s change:%s' % (args, number)
        out, err = self._ssh(cmd)
        if not out:
            return False
        lines = out.split('\n')
        if not lines:
            return False
        data = json.loads(lines[0])
        if not data:
            return False
        iolog = get_annotated_logger(self.iolog, event)
        iolog.debug("Received data from Gerrit query: \n%s",
                    pprint.pformat(data))
        return data

    def queryChangeHTTP(self, number, event=None):
        query = ('changes/%s?o=DETAILED_ACCOUNTS&o=CURRENT_REVISION&'
                 'o=CURRENT_COMMIT&o=CURRENT_FILES&o=LABELS&'
                 'o=DETAILED_LABELS&o=ALL_REVISIONS' % (number,))
        if self.version >= (3, 5, 0):
            query += '&o=SUBMIT_REQUIREMENTS'
        data = self.get(query)
        related = self.get('changes/%s/revisions/%s/related' % (
            number, data['current_revision']))

        files_query = 'changes/%s/revisions/%s/files' % (
            number, data['current_revision'])

        if data['revisions'][data['current_revision']]['commit']['parents']:
            files_query += '?parent=1'

        files = self.get(files_query)
        return data, related, files

    def queryChange(self, number, event=None):
        for attempt in range(3):
            # Get a query ltime -- any events before this point should be
            # included in our change data.
            zuul_query_ltime = self.sched.zk_client.getCurrentLtime()
            try:
                if self.session:
                    data, related, files = self.queryChangeHTTP(
                        number, event=event)
                    return GerritChangeData(GerritChangeData.HTTP,
                                            data, related, files,
                                            zuul_query_ltime=zuul_query_ltime)
                else:
                    data = self.queryChangeSSH(number, event=event)
                    return GerritChangeData(GerritChangeData.SSH, data,
                                            zuul_query_ltime=zuul_query_ltime)
            except Exception:
                if attempt >= 3:
                    raise
                # The internet is a flaky place try again.
                self.log.exception("Failed to query change.")
                time.sleep(1)

    def simpleQuerySSH(self, query, event=None):
        def _query_chunk(query, event):
            args = '--commit-message --current-patch-set'

            cmd = 'gerrit query --format json %s %s' % (
                args, query)
            out, err = self._ssh(cmd)
            if not out:
                return False
            lines = out.split('\n')
            if not lines:
                return False

            # filter out blank lines
            data = [json.loads(line) for line in lines
                    if line.startswith('{')]

            # check last entry for more changes
            more_changes = None
            if 'moreChanges' in data[-1]:
                more_changes = data[-1]['moreChanges']

            # we have to remove the statistics line
            del data[-1]

            if not data:
                return False, more_changes
            iolog = get_annotated_logger(self.iolog, event)
            iolog.debug("Received data from Gerrit query: \n%s",
                        pprint.pformat(data))
            return data, more_changes

        # gerrit returns 500 results by default, so implement paging
        # for large projects like nova
        alldata = []
        chunk, more_changes = _query_chunk(query, event)
        while chunk:
            alldata.extend(chunk)
            if more_changes is None:
                # continue sortKey based (before Gerrit 2.9)
                resume = "resume_sortkey:'%s'" % chunk[-1]["sortKey"]
            elif more_changes:
                # continue moreChanges based (since Gerrit 2.9)
                resume = "-S %d" % len(alldata)
            else:
                # no more changes
                break

            chunk, more_changes = _query_chunk(
                "%s %s" % (query, resume), event)
        return alldata

    def simpleQueryHTTP(self, query, event=None):
        iolog = get_annotated_logger(self.iolog, event)
        changes = []
        sortkey = ''
        done = False
        offset = 0
        query = urllib.parse.quote(query, safe='')
        while not done:
            # We don't actually want to limit to 500, but that's the
            # server-side default, and if we don't specify this, we
            # won't get a _more_changes flag.
            q = ('changes/?n=500%s&o=CURRENT_REVISION&o=CURRENT_COMMIT&'
                 'q=%s' % (sortkey, query))
            iolog.debug('Query: %s', q)
            batch = self.get(q)
            iolog.debug("Received data from Gerrit query: \n%s",
                        pprint.pformat(batch))
            done = True
            if batch:
                changes += batch
                if '_more_changes' in batch[-1]:
                    done = False
                    if '_sortkey' in batch[-1]:
                        sortkey = '&N=%s' % (batch[-1]['_sortkey'],)
                    else:
                        offset += len(batch)
                        sortkey = '&start=%s' % (offset,)
        return changes

    def simpleQuery(self, query, event=None):
        if self.session:
            # None of the users of this method require dependency
            # data, so we only perform the change query and omit the
            # related changes query.
            alldata = self.simpleQueryHTTP(query, event=event)
            return [GerritChangeData(GerritChangeData.HTTP, data)
                    for data in alldata]
        else:
            alldata = self.simpleQuerySSH(query, event=event)
            return [GerritChangeData(GerritChangeData.SSH, data)
                    for data in alldata]

    def _uploadPack(self, project: Project) -> str:
        if self.session and not self.git_over_ssh:
            url = ('%s/%s/info/refs?service=git-upload-pack' %
                   (self.baseurl, project.name))
            r = self.session.get(
                url,
                verify=self.verify_ssl,
                auth=self.auth, timeout=TIMEOUT,
                headers={'User-Agent': self.user_agent})
            self.iolog.debug('Received: %s %s' % (r.status_code, r.text,))
            if r.status_code == 409:
                raise HTTPConflictException()
            elif r.status_code != 200:
                raise Exception("Received response %s" % (r.status_code,))
            out = r.text[r.text.find('\n') + 5:]
        else:
            cmd = "git-upload-pack %s" % project.name
            out, err = self._ssh(cmd, "0000")
        return out

    def _open(self):
        if self.client:
            # Paramiko needs explicit closes, its possible we will open even
            # with an unclosed client so explicitly close here.
            self.client.close()
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
            # SSH banner, handshake, and auth timeouts default to 15
            # seconds, so we only set the socket timeout here.
            client.connect(self.ssh_server,
                           username=self.user,
                           port=self.port,
                           key_filename=self.keyfile,
                           timeout=self.ssh_timeout)
            transport = client.get_transport()
            transport.set_keepalive(self.keepalive)
            self.client = client
        except Exception:
            client.close()
            self.client = None
            raise

    def _ssh(self, command, stdin_data=None, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        if not self.client:
            self._open()

        try:
            log.debug("SSH command:\n%s", command)
            stdin, stdout, stderr = self.client.exec_command(command)
        except Exception:
            self._open()
            stdin, stdout, stderr = self.client.exec_command(command)

        if stdin_data:
            stdin.write(stdin_data)

        out = stdout.read().decode('utf-8')
        self.iolog.debug("SSH received stdout:\n%s" % out)

        ret = stdout.channel.recv_exit_status()
        log.debug("SSH exit status: %s", ret)

        err = stderr.read().decode('utf-8')
        if err.strip():
            log.debug("SSH received stderr:\n%s", err)

        if ret:
            log.debug("SSH received stdout:\n%s", out)
            raise Exception("Gerrit error executing %s" % command)
        return (out, err)

    def getInfoRefs(self, project: Project) -> Dict[str, str]:
        try:
            # Encode the UTF-8 data back to a byte array, as the size of
            # each record in the pack is in bytes, and so the slicing must
            # also be done on a byte-basis.
            data = self._uploadPack(project).encode("utf-8")
        except Exception:
            self.log.error("Cannot get references from %s" % project)
            raise  # keeps error information
        ret = {}
        read_advertisement = False
        i = 0
        while i < len(data):
            if len(data) - i < 4:
                raise Exception("Invalid length in info/refs")
            plen = int(data[i:i + 4], 16)
            i += 4
            # It's the length of the packet, including the 4 bytes of the
            # length itself, unless it's null, in which case the length is
            # not included.
            if plen > 0:
                plen -= 4
            if len(data) - i < plen:
                raise Exception("Invalid data in info/refs")
            # Once the pack data is sliced, we can safely decode it back
            # into a (UTF-8) string.
            line = data[i:i + plen].decode("utf-8")
            i += plen
            if not read_advertisement:
                read_advertisement = True
                continue
            if plen == 0:
                # The terminating null
                continue
            line = line.strip()
            revision, ref = line.split()
            ret[ref] = revision
        return ret

    def getGitUrl(self, project: Project) -> str:
        if self.anonymous_git:
            url = ('%s/%s' % (self.baseurl, project.name))
        elif self.session and not self.git_over_ssh:
            baseurl = list(urllib.parse.urlparse(self.baseurl))
            # Make sure we escape '/' symbols, otherwise git's url
            # parser will think the username is a hostname.
            baseurl[1] = '%s:%s@%s' % (
                urllib.parse.quote(self.user, safe=''),
                urllib.parse.quote(self.password, safe=''),
                baseurl[1])
            baseurl = urllib.parse.urlunparse(baseurl)
            url = ('%s/a/%s' % (baseurl, project.name))
        else:
            url = 'ssh://%s@%s:%s/%s' % (self.user, self.ssh_server, self.port,
                                         project.name)
        return url

    def _getWebUrl(self, project: Project, sha: str=None) -> str:
        return self.gitweb_url_template.format(
            baseurl=self.baseurl,
            project=project.getSafeAttributes(),
            sha=sha)

    def _getRemoteVersion(self):
        version = self.get('config/server/version')
        base = version.split('-')[0]
        parts = base.split('.')
        major = minor = micro = 0
        if len(parts) > 0:
            major = int(parts[0])
        if len(parts) > 1:
            minor = int(parts[1])
        if len(parts) > 2:
            micro = int(parts[2])
        self.version = (major, minor, micro)
        self.log.info("Remote version is: %s (parsed as %s)" %
                      (version, self.version))

    def _getRemoteInfo(self):
        info = self.get('config/server/info')
        change_info = info.get('change', {})
        self.submit_whole_topic = change_info.get('submit_whole_topic', False)
        self.log.info("Remote submitWholeTopic: %s", self.submit_whole_topic)

    def refWatcherCallback(self, data):
        event = {
            'type': 'ref-updated',
            'refUpdate': {
                'project': data['project'],
                'refName': data['ref'],
                'oldRev': data['oldrev'],
                'newRev': data['newrev'],
            }
        }
        self.addEvent(event)

    def onLoad(self, zk_client, component_registry):
        self.log.debug("Starting Gerrit Connection/Watchers")
        if self.session:
            try:
                self._getRemoteVersion()
            except Exception:
                self.log.exception("Unable to determine remote Gerrit version")
            try:
                self._getRemoteInfo()
            except Exception:
                self.log.exception("Unable to fetch remote Gerrit info")

        # Set the project branch cache to read only if no scheduler is
        # provided to prevent fetching the branches from the connection.
        self.read_only = not self.sched

        self.log.debug('Creating Zookeeper branch cache')
        self._branch_cache = BranchCache(zk_client, self,
                                         component_registry)

        self.log.info("Creating Zookeeper event queue")
        self.event_queue = ConnectionEventQueue(
            zk_client, self.connection_name)

        # If the connection was not loaded by a scheduler, but by e.g.
        # zuul-web, we want to stop here.
        if not self.sched:
            return

        self.log.debug('Creating Zookeeper change cache')
        self._change_cache = GerritChangeCache(zk_client, self)

        self.startEventSourceThread()
        # TODO: This is only for the checks plugin and can be removed
        # when checks support is removed.  Until then, we always start
        # this thread, but if no checks are configured, it remains
        # idle.
        self.startPollerThread()
        self.startEventConnector()

    def onStop(self):
        self.log.debug("Stopping Gerrit Connection/Watchers")
        self.stopEventSourceThread()
        self.stopPollerThread()
        self.stopRefWatcherThread()
        self.stopEventConnector()

    def getEventQueue(self):
        return getattr(self, "event_queue", None)

    def stopEventSourceThread(self):
        if self.event_thread:
            self.event_thread.stop()
            self.event_thread.join()

    def startEventSourceThread(self):
        if self.event_source == self.EVENT_SOURCE_STREAM_EVENTS:
            self.startSSHListener()
        elif self.event_source == self.EVENT_SOURCE_KAFKA:
            self.startKafkaListener()
        elif self.event_source == self.EVENT_SOURCE_KINESIS:
            self.startAWSKinesisListener()
        elif self.event_source == self.EVENT_SOURCE_GCLOUD_PUBSUB:
            self.startGcloudPubsubListener()
        else:
            self.log.warning("No gerrit event source configured")
            self.startRefWatcherThread()
        if self.event_thread:
            self.event_thread.start()

    def startSSHListener(self):
        self.log.info("Starting SSH event stream client")
        self.event_thread = GerritSSHEventListener(
            self, self.connection_config)

    def startKafkaListener(self):
        self.log.info("Starting Kafka consumer")
        self.event_thread = GerritKafkaEventListener(
            self, self.connection_config)

    def startAWSKinesisListener(self):
        self.log.info("Starting AWS Kinesis consumer")
        self.event_thread = GerritAWSKinesisEventListener(
            self, self.connection_config)

    def startGcloudPubsubListener(self):
        self.log.info("Starting gcloud pubsub consumer")
        self.event_thread = GerritGcloudPubsubEventListener(
            self, self.connection_config)

    def startPollerThread(self):
        if self.session is not None:
            self.poller_thread = self._poller_class(self)
            self.poller_thread.start()
        else:
            self.log.info(
                "%s: Gerrit Poller is disabled because no "
                "HTTP authentication is defined",
                self.connection_name)

    def stopPollerThread(self):
        if self.poller_thread:
            self.poller_thread.stop()
            self.poller_thread.join()

    def stopRefWatcherThread(self):
        if self.ref_watcher_thread:
            self.ref_watcher_thread.stop()
            self.ref_watcher_thread.join()

    def startRefWatcherThread(self):
        self.ref_watcher_thread = self._ref_watcher_class(
            self,
            self.baseurl,
            self.ref_watcher_poll_interval,
            self.refWatcherCallback,
            election_name="ref-watcher")
        self.ref_watcher_thread.start()

    def startEventConnector(self):
        self.gerrit_event_connector = GerritEventConnector(self)
        self.gerrit_event_connector.start()

    def stopEventConnector(self):
        if self.gerrit_event_connector:
            self.gerrit_event_connector.stop()
            self.gerrit_event_connector.join()
