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
from zuul.source import BaseSource


class GitSource(BaseSource):
    name = 'git'
    log = logging.getLogger("zuul.source.Git")

    def __init__(self, driver, connection, config=None):
        hostname = connection.server.canonical_hostname
        super(GitSource, self).__init__(driver, connection,
                                        hostname, config)

    def getRefSha(self, project, ref):
        raise NotImplemented()

    def isMerged(self, change, head=None):
        raise NotImplemented()

    def canMerge(self, change, allow_needs):
        raise NotImplemented()

    def getChange(self, event, refresh=False):
        raise NotImplemented()

    def getProject(self, name):
        return self.connection.getProject(name)

    def getProjectBranches(self, project):
        return self.connection.getProjectBranches(project)

    def getGitUrl(self, project):
        return self.connection.getGitUrl(project)

    def getProjectOpenChanges(self, project):
        raise NotImplemented()
