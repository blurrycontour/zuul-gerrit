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

from zuul.model import TriggerEvent, EventFilter, RefFilter


class BitbucketServerTriggerEvent(TriggerEvent):
    def __init__(self):
        super().__init__()
        self.trigger_name = 'bitbucketserver'
        self.title = None
        self.action = None
        self.change_number = None


class BitbucketServerEventFilter(EventFilter):
    def __init__(
            self, trigger, types=None, actions=None,
            comments=None, refs=None, ignore_deletes=True):
        super().__init__(self)

    def matches(self, event, change):
        return True


# The RefFilter should be understood as RequireFilter (it maps to
# pipeline requires definition)
class BitbucketServerRefFilter(RefFilter):
    def __init__(self, connection_name, open=None, merged=None, approved=None):
        super().__init__(connection_name)

    def matches(self, change):
        return True
