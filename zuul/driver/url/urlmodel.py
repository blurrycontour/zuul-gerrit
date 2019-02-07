# Copyright 2017 Red Hat, Inc.
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

import re

from zuul.model import EventFilter, TriggerEvent


class URLEventFilter(EventFilter):
    def __init__(self, url, attribute):
        EventFilter.__init__(self, trigger)

        self.url = url
        self.attribute = attribute

    def __repr__(self):
        ret = '<URLEventFilter'
        ret += ' url: %s,' % self.url
        ret += ' attribute: %s' % self.attribute
        ret += '>'
        return ret

    def matches(self, event, change):
        return True


class URLTriggerEvent(TriggerEvent):
    def __init__(self):
        super(URLTriggerEvent, self).__init__()
        self.url = None
        self.attribute = None
