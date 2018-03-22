# Copyright 2019 Red Hat
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

import voluptuous as v

from zuul.driver import Driver, TriggerInterface
from zuul.model import EventFilter, TriggerEvent
from zuul.trigger import BaseTrigger


class WebTriggerDriver(Driver, TriggerInterface):
    name = 'web'

    def getTrigger(self, connection_name, config=None):
        return WebTrigger(self, config)

    def getTriggerSchema(self):
        return v.Any(None)


class WebTriggerFilter(EventFilter):
    def matches(self, event, change):
        if event.type == 'web':
            return True
        return False


class WebTrigger(BaseTrigger):
    name = 'web'

    def getEventFilters(self, trigger_conf):
        return [WebTriggerFilter(self)]


class WebTriggerEvent(TriggerEvent):
    def __init__(self):
        super().__init__()
        self.type = 'web'
