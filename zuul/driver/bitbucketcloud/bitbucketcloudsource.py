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
import re2
import urllib

import logging


class BitbucketCloudSource(BaseSource):
    log = logging.getLogger("zuul.BitbucketCloudSource")

    def __init__(self, driver, connection, config=None):
        hostname = connection.server
        super(BitbucketCloudSource, self).__init__(driver, connection,
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
        return '{}:{}.git'.format(self.connection.cloneurl, project.name)

    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""
        raise NotImplementedError()

    def getChangesDependingOn(self, change, projects, tenant):
        return []

    change_re =\
        re2.compile(r".*/repositories/(.*?)/(.*)/pullrequests/(\d+)[\w]*")

    def getChangeByURL(self, url, event):
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return None
        m = self.change_re.match(parsed.path)
        if not m:
            return None
        workspace = m.group(1)
        repo = m.group(2)
        try:
            pr_number = int(m.group(3))
        except ValueError:
            return None
        project_name = '%s/%s' % (workspace, repo)
        pr = self.connection.getPR(project_name, repo, int(pr_number))
        if not pr:
            return None
        project = self.getProject(project_name)
        change = self.connection._getChange(
            project,
            pr_number,
            patch_number=pr['source']['commit'],
            url=url,
            event=event)
        return change

    def getChange(self, event, refresh=False):
        return self.connection.getChange(event, refresh)

    def canMerge(self, change, allow_needs, event=None):
        """Determine if change can merge."""

        if not change.number:
            # Not a pull request, considering merged.
            return True
        return self.connection.canMerge(change, allow_needs, event=event)

    def isMerged(self, change, head):
        """Determine if change is merged."""
        if not change.number:
            # Not a pull request, considering merged.
            return True
        # We don't need to perform another query because the API call
        # to perform the merge will ensure this is updated.
        return change.is_merged

    def getRejectFilters(self):
        return []

    def getRequireFilters(self):
        return []

    def getCachedChanges(self):
        return []
