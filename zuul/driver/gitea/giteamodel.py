# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
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

from zuul.model import Change, TriggerEvent, EventFilter


EMPTY_GIT_REF = '0' * 40  # git sha of all zeros, used during creates/deletes


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.pr = None
        self.updated_at = None
        self.title = None
        self.body_text = None
        self.reviews = []
        self.files = []
        self.labels = []
        self.draft = None

    def isUpdateOf(self, other):
        if (self.project == other.project and
            hasattr(other, 'number') and self.number == other.number and
            hasattr(other, 'patchset') and self.patchset != other.patchset and
            hasattr(other, 'updated_at') and
            self.updated_at > other.updated_at):
            return True
        return False

    def serialize(self):
        d = super().serialize()
        d.update({
            "pr": self.pr,
            "updated_at": self.updated_at,
            "title": self.title,
            "body_text": self.body_text,
            "reviews": list(self.reviews),
            "labels": self.labels,
            "draft": self.draft,
        })
        return d

    def deserialize(self, data):
        super().deserialize(data)
        self.pr = data.get("pr")
        self.updated_at = data.get("updated_at")
        self.title = data.get("title")
        self.body_text = data.get("body_text")
        self.reviews = data.get("reviews", [])
        self.labels = data.get("labels", [])
        self.draft = data.get("draft")


class GiteaTriggerEvent(TriggerEvent):
    """Incoming event from an external system."""
    def __init__(self):
        super(GiteaTriggerEvent, self).__init__()
        self.title = None
        self.action = None

    def toDict(self):
        d = super().toDict()
        d["title"] = self.title
        d["action"] = self.action

    def updateFromDict(self, d):
        super().updateFromDict(d)
        self.title = d["title"]
        self.action = d["action"]

    def __repr__(self):
        r = [super(GiteaTriggerEvent, self)._repr()]
        if self.action:
            r.append(self.action)
        r.append(self.canonical_project_name)
        if self.change_number:
            r.append('%s,%s' % (self.change_number, self.patch_number))
        return ' '.join(r)


class GiteaEventFilter(EventFilter):
    def __init__(self, connection_name, trigger, types=None, refs=None,
                 ignore_deletes=True):

        super().__init__(connection_name, trigger)

        self._refs = refs
        self.types = types if types is not None else []
        refs = refs if refs is not None else []
        self.refs = [re.compile(x) for x in refs]
        self.ignore_deletes = ignore_deletes

    def __repr__(self):
        ret = '<GiteaEventFilter'
        ret += ' connection: %s' % self.connection_name

        if self.types:
            ret += ' types: %s' % ', '.join(self.types)
        if self._refs:
            ret += ' refs: %s' % ', '.join(self._refs)
        if self.ignore_deletes:
            ret += ' ignore_deletes: %s' % self.ignore_deletes
        ret += '>'

        return ret

    def matches(self, event, change):
        if not super().matches(event, change):
            return False

        # event types are ORed
        matches_type = False
        for etype in self.types:
            if etype == event.type:
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
        if self.ignore_deletes and event.newrev == EMPTY_GIT_REF:
            # If the updated ref has an empty git sha (all 0s),
            # then the ref is being deleted
            return False

        return True
