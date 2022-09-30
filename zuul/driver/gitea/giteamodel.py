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

from zuul.model import Change, TriggerEvent, EventFilter, RefFilter
from zuul.model import FalseWithReason


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
        self.approved = None

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
        if self.approved:
            r.append('approved: true')
        return ' '.join(r) + '>'

    def isUpdateOf(self, other):
        if (self.project == other.project
            and hasattr(other, 'number') and self.number == other.number
            and hasattr(other, 'patchset') and self.patchset != other.patchset
        ):
            # NOTE(gtema): on PR sync updated_at is not representing date of
            # last commit
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
            "approved": self.approved
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
        self.approved = bool(data.get("approved"))


class GiteaTriggerEvent(TriggerEvent):
    """Incoming event from an external system."""
    def __init__(self):
        super(GiteaTriggerEvent, self).__init__()
        self.title = None
        self.action = None
        self.message_edited = None

    def toDict(self):
        d = super().toDict()
        d["title"] = self.title
        d["action"] = self.action
        d["message_edited"] = self.message_edited
        return d

    def updateFromDict(self, d):
        super().updateFromDict(d)
        self.title = d["title"]
        self.action = d["action"]
        self.message_edited = d["message_edited"]

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

    def isChangeAbandoned(self):
        if self.type == 'gt_pull_request':
            return 'closed' == self.action
        return False

    def isMessageChanged(self):
        return bool(self.message_edited)


class GiteaEventFilter(EventFilter):
    def __init__(self, connection_name, trigger, types=None, actions=None,
                 comments=None, refs=None, states=None,
                 ignore_deletes=True):

        super().__init__(connection_name, trigger)

        self._refs = refs
        self.types = types if types is not None else []
        self.actions = actions if actions is not None else []
        self._comments = comments if comments is not None else []
        self.comments = [re.compile(x) for x in self._comments]
        refs = refs if refs is not None else []
        self.refs = [re.compile(x) for x in refs]
        self.ignore_deletes = ignore_deletes
        self.states = states if states else []

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
        if self.states:
            ret += ' states: %s' % ', '.join(self.states)
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
            return FalseWithReason("Type %s doesn't match %s" % (
                self.types, event.type))

        # refs are ORed
        matches_ref = False
        if event.ref is not None:
            for ref in self.refs:
                if ref.match(event.ref):
                    matches_ref = True
        if self.refs and not matches_ref:
            return FalseWithReason("Refs %s doesn't match %s" % (
                self.refs, event.refs))
        if self.ignore_deletes and event.newrev == EMPTY_GIT_REF:
            # If the updated ref has an empty git sha (all 0s),
            # then the ref is being deleted
            return FalseWithReason("Ref deleteions are ignored")

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return FalseWithReason("Action %s doesn't match %s" % (
                self.actions, event.action))

        matches_comment_re = False
        for comment_re in self.comments:
            if (event.comment is not None and
                comment_re.search(event.comment)):
                matches_comment_re = True
        if self.comments and not matches_comment_re:
            return FalseWithReason("Comments %s doesn't match %s" % (
                self.comments, event.comment))

        # states are ORed
        if self.states and event.state not in self.states:
            return FalseWithReason("States %s doesn't match %s" % (
                self.states, event.state))

        return True


# The RefFilter should be understood as RequireFilter (it maps to
# pipeline requires definition)
class GiteaRefFilter(RefFilter):
    def __init__(self, connection_name,
                 open=None, merged=None,
                 approved=None, labels=None):
        RefFilter.__init__(self, connection_name)
        self.open = open
        self.merged = merged
        self.approved = approved
        self.labels = labels or []

    def __repr__(self):
        ret = '<GiteaRefFilter connection_name: %s ' % self.connection_name
        if self.open is not None:
            ret += ' open: %s' % self.open
        if self.merged is not None:
            ret += ' merged: %s' % self.merged
        if self.approved is not None:
            ret += ' approved: %s' % self.approved
        if self.labels is not None:
            ret += ' labels: %s' % self.labels
        ret += '>'
        return ret

    def matches(self, change):
        if self.open is not None:
            if change.open != self.open:
                return FalseWithReason("Change state %s does not match %s" % (
                    self.open, change.open))

        if self.merged is not None:
            if change.is_merged != self.merged:
                return FalseWithReason("Change state %s does not match %s" % (
                    self.merged, change.is_merged))

        if self.approved is not None:
            if change.approved != self.approved:
                return FalseWithReason("Approved %s does not match %s" % (
                    self.approved, change.approved))

        # required labels are ANDed
        for label in self.labels:
            if label not in change.labels:
                return FalseWithReason("Labels %s does not match %s" % (
                    self.labels, change.labels))

        return True
