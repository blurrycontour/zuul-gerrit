# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2012 Hewlett-Packard Development Company, L.P.
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
import re
import urllib

from zuul.driver.gitea.giteamodel import GiteaRefFilter
from zuul.driver.util import scalar_or_list, to_list
from zuul.source import BaseSource
from zuul.model import Project
from zuul.zk.change_cache import ChangeKey


class GiteaSource(BaseSource):
    name = 'gitea'
    log = logging.getLogger("zuul.source.Gitea")

    def __init__(self, driver, connection, config=None):
        hostname = connection.canonical_hostname
        super(GiteaSource, self).__init__(driver, connection,
                                          hostname, config)

    def getRefSha(self, project, ref):
        raise NotImplementedError()

    def isMerged(self, change, head=None):
        """Determine if change is merged."""
        if not change.number:
            # Not a pull request, considering merged.
            return True
        return change.is_merged

    def canMerge(self, change, allow_needs, event=None, allow_refresh=False):
        """Determine if change can merge."""
        if not change.number:
            # Not a pull request, considering merged.
            return True
        return self.connection.canMerge(change, allow_needs, event=event)

    def getChangeKey(self, event):
        self.log.debug("getChangeKey for %s" % (event))
        connection_name = self.connection.connection_name
        if event.change_number:
            return ChangeKey(connection_name, event.project_name,
                             'PullRequest',
                             str(event.change_number),
                             str(event.patch_number))
        revision = f'{event.oldrev}..{event.newrev}'
        if event.ref and event.ref.startswith('refs/tags/'):
            tag = event.ref[len('refs/tags/'):]
            return ChangeKey(connection_name, event.project_name,
                             'Tag', tag, revision)
        if event.ref and event.ref.startswith('refs/heads/'):
            branch = event.ref[len('refs/heads/'):]
            return ChangeKey(connection_name, event.project_name,
                             'Branch', branch, revision)
        if event.ref:
            return ChangeKey(connection_name, event.project_name,
                             'Ref', event.ref, revision)

        self.log.warning("Unable to format change key for %s" % (self,))

    def getChange(self, change_key, refresh=False, event=None):
        return self.connection.getChange(change_key, refresh=refresh,
                                         event=event)

    change_re = re.compile(r"/(.*?)/(.*?)/pulls/(\d+)[\w]*")

    def getChangeByURL(self, url, event):
        self.log.debug("getChangeByURL %s [%s]" % (url, event))
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return None
        m = self.change_re.match(parsed.path)
        if not m:
            return None
        org = m.group(1)
        proj = m.group(2)
        try:
            num = int(m.group(3))
        except ValueError:
            return None
        pull = self.connection.getPull(
            '%s/%s' % (org, proj), int(num), event=event)
        if not pull:
            return None
        proj = pull.get('base').get('repo').get('full_name')
        change_key = ChangeKey(self.connection.connection_name, proj,
                               'PullRequest',
                               str(num),
                               pull.get('head').get('sha'))
        change = self.connection._getChange(change_key, event=event)
        return change

    def getChangesDependingOn(self, change, projects, tenant):
        return self.connection.getChangesDependingOn(change, projects, tenant)

    def getCachedChanges(self):
        return list(self.connection._change_cache)

    def getProject(self, name):
        p = self.connection.getProject(name)
        if not p:
            p = Project(name, self)
            self.connection.addProject(p)
        return p

    def getProjectBranches(self, project, tenant, min_ltime=-1):
        return self.connection.getProjectBranches(project, tenant, min_ltime)

    def getProjectBranchCacheLtime(self):
        return self.connection._branch_cache.ltime

    def getGitUrl(self, project):
        return self.connection.getGitUrl(project)

    def getProjectOpenChanges(self, project):
        raise NotImplementedError()

    def getRequireFilters(self, config):
        f = GiteaRefFilter(
            connection_name=self.connection.connection_name,
            open=config.get('open'),
            merged=config.get('merged'),
            approved=config.get('approved'),
            labels=to_list(config.get('labels')),
        )
        return [f]

    def getRejectFilters(self, config):
        f = GiteaRefFilter(
            connection_name=self.connection.connection_name,
            open=config.get('open'),
            merged=config.get('merged'),
            approved=config.get('approved'),
            labels=to_list(config.get('labels')),
        )
        return [f]

    def getRefForChange(self, change):
        raise NotImplementedError()
        # return "refs/pull/%s/head" % change


# Require model
def getRequireSchema():
    require = {
        'open': bool,
        'merged': bool,
        'approved': bool,
        'labels': scalar_or_list(str)
    }
    return require


# Reject model
def getRejectSchema():
    reject = {
        'open': bool,
        'merged': bool,
        'approved': bool,
        'labels': scalar_or_list(str)
    }
    return reject
