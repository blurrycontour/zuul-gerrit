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
class BaseTrigger(object):
    """Base class for triggers.

    Defines the exact public methods that must be supplied."""
    @abc.abstractmethod
    def __init__(self, trigger_config={}):
        self.trigger_config = trigger_config

    @abc.abstractmethod
    def stop(self):
        """Stop the trigger."""

    @abc.abstractmethod
    def getEventFilters(self, trigger_conf):
        raise NotImplementedError()

    @abc.abstractmethod
    def postConfig(self):
        """Called after config is loaded."""

    @abc.abstractmethod
    def onChangeMerged(self, change, source):
        raise NotImplementedError()

    @abc.abstractmethod
    def onChangeEnqueued(self, change, pipeline):
        """Called when a change has been enqueued."""
        raise NotImplementedError()

    @abc.abstractmethod
    def registerScheduler(self, sched):
        self.sched = sched

    @abc.abstractmethod
    def registerConnection(self, connection):
        self.connection = connection
