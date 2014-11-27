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


class BaseReporter(object):
    """Base class for reporters.

    Defines the exact public methods that must be supplied."""

    def __init__(self, reporter_config={}):
        self.reporter_config = reporter_config

    def report(self, source, change, message, params):
        """Send the compiled report message."""
        raise NotImplementedError()

    def getSubmitAllowNeeds(self, params):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return []

    def postConfig(self):
        """Run tasks after configuration is reloaded"""
        raise NotImplementedError()

    def registerScheduler(self, sched):
        self.sched = sched

    def registerConnection(self, connection):
        self.connection = connection
