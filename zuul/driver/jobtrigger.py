# Copyright 2018 Red Hat
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

import voluptuous

from zuul.driver import Driver, TriggerInterface
from zuul.model import EventFilter
from zuul.trigger import BaseTrigger


class JobTriggerDriver(Driver, TriggerInterface):
    name = 'job-trigger'

    def getTrigger(self, connection_name, config=None):
        return JobTrigger(self, config)

    def getTriggerSchema(self):
        return voluptuous.Any(None)


class JobTrigger(BaseTrigger):
    name = 'job-trigger'

    def getEventFilters(self, trigger_conf):
        return [JobTriggerFilter(self)]


class JobTriggerFilter(EventFilter):
    def matches(self, event, change):
        if change.type == "job":
            return True
        return False
