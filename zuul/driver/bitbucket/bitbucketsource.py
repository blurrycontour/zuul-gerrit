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
import urllib

import re2

from zuul.source import BaseSource
from zuul.model import Ref, Branch, Tag

from zuul.driver.bitbucket.bitbucketmodel import BitbucketChangeFilter


class BitbucketSource(BaseSource):
    change_re = \
        re2.compile(r".*/projects/(.*?)/repos/(.*?)/pull-requests/(\d+)[\w]*")

    def __init__(self, driver, connection, config=None):
        hostname = connection.server
        self.log = logging.getLogger('zuul.BitbucketSource')
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
        return self.connection.getGitUrl(project)

    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""
        return self.connection.getProjectOpenChanges(project)

    def getChangesDependingOn(self, change, projects, tenant):
        return []

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
        change = self.connection.buildPR(project, repo, int(id))

        return change

    def getChange(self, event, refresh=False):
        if event.type in ['bb-pr', 'bb-comment']:
            project_name, repo = self.connection._getProjectRepo(
                event.project_name)
            return self.connection.buildPR(
                project_name, repo, event.change_id)

        else:
            self.log.info("Getting change for %s ref:%s" % (
                event.project_name, event.ref))
            if event.ref and event.ref.startswith('refs/tags/'):
                change = Tag(self.getProject(event.project_name))
                change.tag = event.ref[len('refs/tags/'):]
            elif event.ref and event.ref.startswith('refs/heads/'):
                change = Branch(self.getProject(event.project_name))
                change.branch = event.ref[len('refs/heads/'):]
            else:
                change = Ref(self.getProject(event.project_name))
            change.ref = event.ref
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.branch = event.branch
            change.url = ''
            return change

        return None

    def canMerge(self, change, allow_needs):
        return self.connection.canMerge(change, allow_needs)

    def isMerged(self, change, head):
        return self.connection.isMerged(change, head)

    def getRejectFilters(self, config):
        return []

    def getRequireFilters(self, config):
        f = BitbucketChangeFilter(
            connection_name=self.connection.connection_name,
            open=config.get('open'),
            closed=config.get('closed'),
            status=config.get('status'),
            canMerge=config.get('canMerge'),
        )
        return [f]


# require model
def getRequireSchema():
    require = {
        'open': bool,
        'closed': bool,
        'status': str,
        'canMerge': bool
    }
    return require


def getRejectSchema():
    reject = {}
    return reject
