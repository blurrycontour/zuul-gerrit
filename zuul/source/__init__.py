# Copyright 2014 Rackspace Australia
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


class BaseSource(object):
    """Base class for sources.

    Defines the exact public methods that must be supplied."""

    def getRefSha(self, project, ref):
        raise NotImplementedError()

    def waitForRefSha(self, project, ref, old_sha=''):
        raise NotImplementedError()

    def isMerged(self, change, head=None):
        raise NotImplementedError()

    def canMerge(self, change, allow_needs):
        raise NotImplementedError()

    def maintainCache(self, relevant):
        pass

    def postConfig(self):
        pass

    def getChange(self, event, project):
        raise NotImplementedError()

    def getProjectOpenChanges(self, project):
        raise NotImplementedError()

    def updateChange(self, change):
        raise NotImplementedError()

    def getGitUrl(self, project):
        raise NotImplementedError()

    def getGitwebUrl(self, project, sha=None):
        raise NotImplementedError()

    def registerScheduler(self, sched):
        self.sched = sched

    def registerConnection(self, connection):
        self.connection = connection
