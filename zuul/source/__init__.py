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

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class BaseSource(object):
    """Base class for sources.

    Defines the exact public methods that must be supplied."""

    @abc.abstractmethod
    def __init__(self, config, sched):
        """Constructor."""

    @abc.abstractmethod
    def getRefSha(self, project, ref):
        """Return a sha for a given project ref."""

    @abc.abstractmethod
    def waitForRefSha(self, project, ref, old_sha=''):
        """Block until a ref shows up in a given project."""

    @abc.abstractmethod
    def isMerged(self, change, head=None):
        """Determine if change is merged."""

    @abc.abstractmethod
    def canMerge(self, change, allow_needs):
        """Determine if change can merge."""

    def maintainCache(self, relevant):
        pass

    def postConfig(self):
        pass

    @abc.abstractmethod
    def getChange(self, event, project):
        """Get the change representing an event."""

    @abc.abstractmethod
    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""

    @abc.abstractmethod
    def updateChange(self, change, history=None):
        """Update information for a change."""

    @abc.abstractmethod
    def getGitUrl(self, project):
        """Get the git url for a project."""

    @abc.abstractmethod
    def getGitwebUrl(self, project, sha=None):
        """Get the git-web url for a project."""
