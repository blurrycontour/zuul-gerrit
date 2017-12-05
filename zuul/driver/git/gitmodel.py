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

from zuul.model import TriggerEvent
from zuul.model import EventFilter


EMPTY_GIT_REF = '0' * 40  # git sha of all zeros, used during creates/deletes


class GitTriggerEvent(TriggerEvent):
    """Incoming event from an external system."""
    def __init__(self):
        super(GitTriggerEvent, self).__init__()

    def __repr__(self):
        ret = '<GitTriggerEvent %s %s' % (self.type,
                                          self.project_name)

        if self.branch:
            ret += " %s" % self.branch
        ret += '>'

        return ret


class GitEventFilter(EventFilter):
    def __init__(self, trigger, types=[], refs=[]):

        EventFilter.__init__(self, trigger)

        self._types = types
        self._refs = refs
        self.types = [re.compile(x) for x in types]
        self.refs = [re.compile(x) for x in refs]

    def __repr__(self):
        ret = '<GerritEventFilter'

        if self._types:
            ret += ' types: %s' % ', '.join(self._types)
        if self._refs:
            ret += ' refs: %s' % ', '.join(self._refs)
        ret += '>'

        return ret

    def matches(self, event, change):
        # event types are ORed
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return False

        # refs are ORed
        matches_ref = False
        if event.ref is not None:
            for ref in self.refs:
                if ref.match(event.ref):
                    matches_ref = True
        if self.refs and not matches_ref:
            return False

        return True
