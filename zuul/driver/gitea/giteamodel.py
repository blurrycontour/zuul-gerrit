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
        self.reviews = []
        self.files = []
        self.labels = []
        self.draft = None
        self.required_contexts = set()
        self.require_status_check = False
        self.required_approvals = 0
        self.contexts = set()
        self.branch_protected = False

    def __repr__(self):
        r = ['<Change 0x%x' % id(self)]
        if self.project:
            r.append('project: %s' % self.project)
        if self.number:
            r.append('number: %s' % self.number)
        if self.patchset:
            r.append('patchset: %s' % self.patchset)
        if self.updated_at:
            r.append('updated: %s' % self.updated_at)
        if self.open:
            r.append('state: open')
        return ' '.join(r) + '>'

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
            "reviews": list(self.reviews),
            "labels": self.labels,
            "draft": self.draft,
            "required_contexts": list(self.required_contexts),
            "required_approvals": int(self.required_approvals),
            "required_status_check": self.require_status_check,
            "contexts": list(self.contexts),
            "branch_protected": self.branch_protected,
        })
        return d

    def deserialize(self, data):
        super().deserialize(data)
        self.pr = data.get("pr")
        self.updated_at = data.get("updated_at")
        self.title = data.get("title")
        self.reviews = data.get("reviews", [])
        self.labels = data.get("labels", [])
        self.draft = data.get("draft")
        self.required_contexts = set(data.get("required_contexts", []))
        self.required_approvals = int(data.get("required_approvals", 0))
        self.required_status_check = bool(
            data.get("required_status_check", False))
        self.contexts = set(tuple(c) for c in data.get("contexts", []))
        self.branch_protected = data.get("branch_protected", False)


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
        return d

    def updateFromDict(self, d):
        super().updateFromDict(d)
        self.title = d["title"]
        self.action = d["action"]

    def _repr(self):
        r = [super(GiteaTriggerEvent, self)._repr()]
        if self.action:
            r.append(self.action)
        if self.change_number:
            r.append('%s,%s' % (self.change_number, self.patch_number))
        return ' '.join(r)

    def isPatchsetCreated(self):
        if self.type == 'gt_pull_request':
            return self.action in ['opened', 'changed']
        return False


class GiteaEventFilter(EventFilter):
    def __init__(self, connection_name, trigger, types=None, actions=None,
                 comments=None, refs=None, ignore_deletes=True):

        super().__init__(connection_name, trigger)

        self._refs = refs
        self.types = types if types is not None else []
        self.actions = actions if actions is not None else []
        self._comments = comments if comments is not None else []
        self.comments = [re.compile(x) for x in self._comments]
        refs = refs if refs is not None else []
        self.refs = [re.compile(x) for x in refs]
        self.ignore_deletes = ignore_deletes

    def __repr__(self):
        ret = '<GiteaEventFilter'
        ret += ' connection: %s' % self.connection_name

        if self.types:
            ret += ' types: %s' % ', '.join(self.types)
        if self.actions:
            ret += ' actions: %s' % ', '.join(self.actions)
        if self._comments:
            ret += ' comments: %s' % ', '.join(self._comments)
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

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return False

        matches_comment_re = False
        for comment_re in self.comments:
            if (event.comment is not None and
                comment_re.search(event.comment)):
                matches_comment_re = True
        if self.comments and not matches_comment_re:
            return False

        return True
