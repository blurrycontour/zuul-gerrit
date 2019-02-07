# Copyright 2019 Red Hat, Inc.
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

from zuul.model import EventFilter, TriggerEvent


class URLEventFilter(EventFilter):
    def __init__(self, trigger, _type, time, url, header_field):
        EventFilter.__init__(self, trigger)

        self.type = _type
        self.time = time
        self.url = url
        self.header_field = header_field

    def __repr__(self):
        ret = '<URLEventFilter'
        ret += ' type: %s' % self.type
        ret += ' time: %s' % self.time
        ret += ' url: %s,' % self.url
        ret += ' header_field: %s' % self.header_field
        ret += '>'
        return ret

    def matches(self, event, change):
        if event.type != self.type:
            return False
        return True


class URLTriggerEvent(TriggerEvent):
    def __init__(self):
        super(URLTriggerEvent, self).__init__()
        self.time = None
        self.url = None
        self.header_field = None
