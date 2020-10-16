# Copyright 2020 Motional.
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


class BitbucketServerSource(BaseSource):
    name = 'bitbucketserver'
    log = logging.getLogger("zuul.source.BitbucketServerSource")

    def __init__(self, driver, connection, config=None):
        super().__init__(driver, connection, '', config)

    def getRefSha(self, project, ref):
        raise NotImplementedError()

    def isMerged(self, change, head=None):
        raise NotImplementedError()

    def canMerge(self, change, allow_needs, event=None):
        raise NotImplementedError()

    def postConfig(self):
        raise NotImplementedError()

    def getChange(self, event, refresh=False):
        raise NotImplementedError()

    def getChangeByURL(self, url, event):
        raise NotImplementedError()

    def getChangesDependingOn(self, change, projects, tenant):
        raise NotImplementedError()

    def getProjectOpenChanges(self, project):
        raise NotImplementedError()

    def getGitUrl(self, project):
        raise NotImplementedError()

    def getProject(self, name):
        raise NotImplementedError()

    def getProjectBranches(self, project, tenant):
        raise NotImplementedError()

    def getRequireFilters(self, config):
        raise NotImplementedError()

    def getRejectFilters(self, config):
        raise NotImplementedError()

    def getRefForChange(self, change):
        raise NotImplementedError()


def getRequireSchema():
    require = {}
    return require


def getRejectSchema():
    reject = {}
    return reject
