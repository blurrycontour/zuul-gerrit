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

from zuul.source import BaseSource
from zuul.driver.bitbucket.bitbucketmodel import PullRequest
import re2
import urllib


class BitbucketSource(BaseSource):

    change_re =\
        re2.compile(r".*/projects/(.*?)/repos/(.*?)/pull-requests/(\d+)[\w]*")

    def __init__(self, driver, connection, config=None):
        hostname = connection.server
        super(BitbucketSource, self).__init__(driver, connection,
                                              hostname, config)

    def getRefSha(self, project, ref):
        """Return a sha for a given project ref."""
        raise NotImplementedError()

    def waitForRefSha(self, project, ref, old_sha=''):
        """Block until a ref shows up in a given project."""
        raise NotImplementedError()

    def getProject(self, name):
        return self.connection.getProject(name)

    def getProjectBranches(self, project, tenant):
        return self.connection.getProjectBranches(project.name, tenant)

    def getGitUrl(self, project):
        return '{}/{}.git'.format(self.connection.cloneurl, project.name)

    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""
        bb_proj, repo = self.connection._getProjectRepo(project.name)
        prs = self.connection.getPRs(bb_proj, repo)

        return [self.buildPR(bb_proj, repo, pr.get('id'))
                for pr in prs.get('values')]

    def getChangesDependingOn(self, change, projects, tenant):
        return []

    def buildPR(self, project, repo, id):
        pr = self.connection.getPR(project, repo, id)

        project = self.getProject('{}/{}'.format(project, repo))
        pull = PullRequest(project.name)
        pull.project = project
        pull.id = id
        pull.updatedDate = pr.get('updatedDate')
        fromProj = '{}/{}'.format(pr.get('fromRef').get('repository')
                                  .get('project').get('key'),
                                  pr.get('fromRef').get('repository')
                                  .get('slug'))
        bslug = self.connection.getBranchSlug(fromProj, pr.get('fromRef')
                                              .get('id'))
        pull.patchset = self.connection.getBranchSha(fromProj, bslug)
        pull.title = pr.get('title')

        return pull

    def getChangeByURL(self, url):
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return None
        m = self.change_re.match(parsed.path)
        if not m:
            return None
        project = m.group(1)
        repo = m.group(2)
        try:
            id = int(m.group(3))
        except ValueError:
            return None
        change = self.buildPR(project, repo, int(id))

        return change

    def getChange(self, event):
        raise NotImplementedError()

    def canMerge(self, change, allow_needs):
        return self.connection.canMerge(change, allow_needs)

    def isMerged(self, change, head):
        return self.connection.isMerged(change, head)

    def getRejectFilters(self):
        return []

    def getRequireFilters(self):
        return []
