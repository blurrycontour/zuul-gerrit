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

from zuul.connection import BaseConnection
from zuul.model import Project
from zuul.exceptions import MergeFailure

from zuul.driver.bitbucket.bitbucketsource import BitbucketSource

import logging
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse


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
        r = requests.get(url, auth=HTTPBasicAuth(self.user, self.pw))

        if r.status_code != 200:
            raise BitbucketConnectionError(
                "Connection to server returned status {} path {}"
                .format(r.status_code, url))

        return r.json()

    def post(self, path, payload):
        url = '{}:{}{}'.format(self.baseurl, path)
        r = requests.post(url, auth=HTTPBasicAuth(self.user, self.pw),
                          data=payload)

        if r.status_code != requests.codes.ok:
            raise BitbucketConnectionError(
                "Connection to server returned status {} path {}"
                .format(r.status_code, url))

        return r.json()


class BitbucketConnection(BaseConnection):
    driver_name = 'bitbucket'
    log = logging.getLogger("zuul.BitbucketConnection")

    def __init__(self, driver, connection_name, connection_config):
        super(BitbucketConnection, self).__init__(
            driver, connection_name, connection_config)
        self.projects = {}

        self.base_url = self.connection_config.get('baseurl').rstrip('/')
        self.cloneurl = self.connection_config.get('cloneurl').rstrip('/')
        self.server_user = self.connection_config.get('user')
        self.server_pass = self.connection_config.get('password')

        up = urlparse(self.base_url)
        self.server = up.netloc

        self.source = BitbucketSource(driver, self)

        self.branches = {}

    def _getBitbucketClient(self):
        # authenticate, return client
        client = BitbucketClient(self.base_url)
        client.setCredentials(self.server_user, self.server_pass)
        return client

    def _getProjectRepo(self, project_name):
        project, repo = project_name.split('/', 2)
        return project, repo

    def onLoad(self):
        pass

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

    def getPR(self, project, repo, id):
        return self._getBitbucketClient()\
            .get('/rest/api/1.0/projects/{}/repos/{}/pull-requests/{}'
                 .format(project, repo, id))

    def getPRs(self, project, repo):
        return self._getBitbucketClient()\
            .get('/rest/api/1.0/projects/{}/repos/{}/pull-requests'
                 .format(project, repo))

    def canMerge(self, change, allow_needs):
        bb_proj, repo = self._getProjectRepo(change.project.name)
        can_merge = self._getBitbucketClient()\
            .get('/rest/api/1.0/projects/{}/repos/{}/pull-requests/{}/merge'
                 .format(bb_proj, repo, change.id))

        return can_merge.get('canMerge')

    def isMerged(self, change, head):
        bb_proj, repo = self._getProjectRepo(change.project.name)
        pr = self.getPR(bb_proj, repo, change.id)

        return pr.get('state') == 'MERGED'

    def reportBuild(self, commitHash, status):
        client = self._getBitbucketClient()

        client.post('/rest/build-status/1.0/commits/{}'.format(commitHash),
                    status)

    def mergePull(self, projectName, prId):
        client = self._getBitbucketClient()

        project, repo = self._getProjectRepo(projectName)

        re = client.post('/rest/api/1.0/projects/{}/repos/{}/pull'
                         '-requests/{}/merge',
                         project, repo, prId)

        if re.get('state') != 'MERGED':
            raise MergeFailure()

        return True
