# Copyright 2019 Smaato, Inc.
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
import time
import traceback
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

from zuul.connection import BaseConnection
from zuul.driver.bitbucket.bitbucketmodel import BitbucketTriggerEvent, \
    PullRequest
from zuul.driver.bitbucket.bitbucketsource import BitbucketSource
from zuul.exceptions import MergeFailure
from zuul.model import Project


class BitbucketWatcher(threading.Thread):
    log = logging.getLogger("zuul.connection.bitbucket.watcher")

    def __init__(self, bitbucket_con, poll_delay):
        threading.Thread.__init__(self)

        self.daemon = True
        self.bitbucket_con = bitbucket_con
        self.poll_delay = poll_delay
        self.stopped = False
        self.branches = self.bitbucket_con.branches
        self.event_count = 0

    def isNew(self, change):
        projectname = change.project.name
        prid = change.id

        return (self.bitbucket_con.cachedPR(projectname, prid)
                is None)

    def supersedes(self, change):
        projectname = change.project.name
        prid = change.id

        oldpr = self.bitbucket_con.cachedPR(projectname, prid)
        if oldpr and change.isUpdateOf(oldpr):
            return oldpr

        return None

    def _handleBasePR(self, change):
        event = BitbucketTriggerEvent()
        event.type = 'bb-pr'
        event.title = change.title
        event.project_name = change.project.name
        event.change_id = change.id
        event.updateDate = change.updatedDate
        event.branch = change.branch
        event.ref = change.patchset
        event.project_hostname = self.bitbucket_con.canonical_hostname

        return event

    def _handleNewPR(self, change):
        event = self._handleBasePR(change)

        event.action = 'opened'

        self.log.debug('New event: {}'.format(event))

        self.bitbucket_con.sched.addEvent(event)

        return event

    def _handleUpdatePR(self, change, oldchange):
        event = self._handleBasePR(change)

        event.action = 'updated'

        self.log.debug('New event {}'.format(event))

        self.bitbucket_con.sched.addEvent(event)

    def _run(self):
        self.log.debug("Check for updates: {}"
                       .format(self.bitbucket_con.connection_name))
        try:
            for p in self.bitbucket_con.projects:
                project = self.bitbucket_con.getProject(p)
                for change in self.bitbucket_con.getProjectOpenChanges(
                        project, False):
                    if self.isNew(change):
                        self.log.debug(
                            "New change: {} in {}".format(
                                change, change.project)
                        )
                        self._handleNewPR(change)
                        return
                    oldpr = self.supersedes(change)
                    if oldpr:
                        self._handleUpdatePR(change, oldpr)
                        return

        except Exception as e:
            self.log.debug("Unexpected issue in _run loop: {}"
                           .format(str(e))
                           )
            self.log.debug(traceback.format_exception(Exception, e))

    # core event loop, no unittest
    def run(self):
        while not self.stopped:
            if not self.bitbucket_con.pause_watcher:
                self._run()
            else:
                self.log.debug("Watcher is paused")
            time.sleep(self.poll_delay)

    # core event loop, no unittest
    def stop(self):
        self.stopped = True


class BitbucketConnectionError(BaseException):
    def __init__(self, message):
        self.message = message


class BitbucketClient():
    def __init__(self, baseurl):
        self.baseurl = baseurl

    def setCredentials(self, user, pw):
        self.user = user
        self.pw = pw

    def get(self, path):
        url = '{}{}'.format(self.baseurl, path)
        r = requests.get(url, auth=HTTPBasicAuth(self.user, self.pw),
                         timeout=1)

        if r.status_code != 200:
            raise BitbucketConnectionError(
                "Connection to server returned status {} path {}"
                .format(r.status_code, url)
            )

        return r.json()

    def post(self, path, payload):
        url = '{}{}'.format(self.baseurl, path)
        retries = 0
        retry = True
        while retry and retries < 3:
            try:
                r = requests.post(url, auth=HTTPBasicAuth(self.user, self.pw),
                                  json=payload, timeout=1)
                retry = False
            except requests.exceptions.Timeout:
                retries = retries + 1

        if r.status_code not in [200, 201, 204]:
            raise BitbucketConnectionError(
                "Connection to server returned status {} path {}"
                .format(r.status_code, url))

        if r.status_code == 200:
            return r.json()
        else:
            return None


class BitbucketConnection(BaseConnection):
    driver_name = 'bitbucket'
    log = logging.getLogger("zuul.BitbucketConnection")

    def __init__(self, driver, connection_name, connection_config):
        super(BitbucketConnection, self).__init__(
            driver, connection_name, connection_config
        )
        self.projects = {}
        self.prs = {}

        self.base_url = self.connection_config.get('baseurl').rstrip('/')
        self.cloneurl = self.connection_config.get('cloneurl').rstrip('/')
        self.server_user = self.connection_config.get('user')
        self.server_pass = self.connection_config.get('password')

        up = urlparse(self.base_url)
        self.server = up.netloc

        self.source = BitbucketSource(driver, self)

        self.branches = {}

        self.pause_watcher = False

        self.poll_delay = 60

        self.canonical_hostname = up.netloc

        self.watcher_thread = BitbucketWatcher(self, self.poll_delay)

    def _getBitbucketClient(self):
        # authenticate, return client
        client = BitbucketClient(self.base_url)
        client.setCredentials(self.server_user, self.server_pass)
        return client

    def _getProjectRepo(self, project_name):
        project, repo = project_name.split('/', 2)
        return project, repo

    def onLoad(self):
        self.log.debug("Starting Bitbucket watcher")
        self._start_watcher_thread()

    def onStop(self):
        self.log.debug("Stopping Bitbucket watcher")
        self._stop_watcher_thread()

    def _start_watcher_thread(self):
        self.watcher_thread = BitbucketWatcher(
            self, self.poll_delay)
        self.watcher_thread.start()

    def _stop_watcher_thread(self):
        if self.watcher_thread:
            self.watcher_thread.stop()
            self.watcher_thread.join()

    def clearBranchCache(self):
        self.projects = {}

    def getProject(self, name):
        if name not in self.projects:
            self.projects[name] = Project(name, self.source)
        return self.projects.get(name)

    def getBranchSlug(self, project, id):
        self.getProjectBranches(project, 'default')
        for branch in self.branches[project].keys():
            if self.branches[project][branch].get('id') == id:
                return self.branches[project][branch].get('displayId')

        return None

    def getBranchSha(self, project, branch):
        self.getProjectBranches(project, 'default')

        return self.branches[project][branch].get('latestCommit')

    def getProjectBranches(self, project, tenant):
        client = self._getBitbucketClient()
        bb_project, repo = self._getProjectRepo(project)
        res = client.get('/rest/api/1.0/projects/{}/repos/{}/branches'
                         .format(bb_project, repo))

        project_branches = self.branches.get(project, {})
        for item in res.get('values'):
            project_branches[item.get('displayId')] = item
        self.branches[project] = project_branches

        return [item.get('displayId') for item in res.get('values')
                if item.get('type') == 'BRANCH']

    def buildPR(self, project, repo, id, cache=True):
        pr = self.getPR(project, repo, id)

        project = self.getProject('{}/{}'.format(project, repo))
        pull = PullRequest(project.name)
        pull.project = project
        pull.id = id
        pull.number = id
        pull.updatedDate = pr.get('updatedDate')
        fromProj = '{}/{}'.format(pr.get('fromRef').get('repository')
                                  .get('project').get('key'),
                                  pr.get('fromRef').get('repository')
                                  .get('slug'))
        bslug = self.getBranchSlug(fromProj, pr.get('fromRef')
                                   .get('id'))
        pull.patchset = self.getBranchSha(fromProj, bslug)
        b = pr.get('fromRef').get('id')
        if b.startswith('refs/heads/'):
            pull.branch = b[len('refs/heads/'):]
        else:
            pull.branch = b
        pull.title = pr.get('title')
        pull.message = pr.get('description', '')

        if cache:
            self.cachePR(pull)

        return pull

    def getProjectOpenChanges(self, project, cache=True):
        bb_proj, repo = self._getProjectRepo(project.name)
        prs = self.getPRs(bb_proj, repo)

        return [self.buildPR(bb_proj, repo, pr.get('id'), cache)
                for pr in prs.get('values')]

    def getPR(self, project, repo, id):
        return self._getBitbucketClient().get(
            '/rest/api/1.0/projects/{}/repos/{}/pull-requests/{}'
            .format(project, repo, id)
        )

    def getPRs(self, project, repo):
        return self._getBitbucketClient().get(
            '/rest/api/1.0/projects/{}/repos/{}/pull-requests'
            .format(project, repo)
        )

    def cachePR(self, pr):
        projecthash = self.prs.get(pr.project.name, {})
        projecthash[pr.id] = pr
        self.prs[pr.project.name] = projecthash

    def cachedPR(self, projectname, prid):
        if projectname in self.prs:
            if prid in self.prs[projectname]:
                return self.prs[projectname][prid]

        return None

    def canMerge(self, change, allow_needs):
        bb_proj, repo = self._getProjectRepo(change.project.name)
        can_merge = self._getBitbucketClient().get(
            '/rest/api/1.0/projects/{}/repos/{}/pull-requests/{}/merge'
            .format(bb_proj, repo, change.id)
        )

        return can_merge.get('canMerge')

    def isMerged(self, change, head):
        bb_proj, repo = self._getProjectRepo(change.project.name)
        pr = self.getPR(bb_proj, repo, change.id)

        return pr.get('state') == 'MERGED'

    def reportBuild(self, commitHash, status):
        client = self._getBitbucketClient()

        client.post('/rest/build-status/1.0/commits/{}'.format(commitHash),
                    status)

    def commentPR(self, project, prid, message):
        client = self._getBitbucketClient()

        project_name, repo = self._getProjectRepo(project)

        client.post(
            '/rest/api/1.0/projects/{}/repos/{}/pull-requests/{}/comments'
            .format(project_name, repo, prid), {'text': message}
        )

    def mergePull(self, projectName, prId):
        client = self._getBitbucketClient()

        project, repo = self._getProjectRepo(projectName)

        re = client.post('/rest/api/1.0/projects/{}/repos/{}/pull'
                         '-requests/{}/merge',
                         project, repo, prId)

        if re.get('state') != 'MERGED':
            raise MergeFailure()

        return True
