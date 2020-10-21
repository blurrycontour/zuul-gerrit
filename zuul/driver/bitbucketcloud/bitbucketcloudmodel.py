# Copyright 2019 Smaato, Inc.
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

from zuul.model import Change, EventFilter, TriggerEvent, FalseWithReason
import re2
import logging


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.project = None
        self.pr = None
        self.updated_at = None
        self.title = None
        self.body_text = None
        self.reviews = []
        self.files = []
        self.updated_at = None
        self.id = None

    def isUpdateOf(self, other):
        if (self.project == other.project and
                hasattr(other, 'id') and self.id == other.id and
                hasattr(other, 'patchset') and
                self.patchset != other.patchset and
                hasattr(other, 'updatedDate') and
                self.updated_at > other.updated_at):
            return True
        return False


class BitbucketCloudEventFilter(EventFilter):

    log = logging.getLogger("zuul.BitbucketCloudEventFilter")

    def __init__(self, trigger, types=[], branches=[],
                 comments=[], actions=[], refs=[]):
        EventFilter.__init__(self, trigger)

        self._types = types
        self._branches = branches
        self._comments = comments
        self.types = [re2.compile(x) for x in types]
        self.branches = [re2.compile(x) for x in branches]
        self.comments = [re2.compile(x) for x in comments]
        self.actions = actions
        self._refs = refs
        self.refs = [re2.compile(x) for x in refs]

    def matches(self, event, change):
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return FalseWithReason("Types %s doesn't match %s" % (
                self.types, event.type))

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return FalseWithReason("Actions %s doesn't match %s" % (
                self.actions, event.action))

        matches_branch = False
        for branch in self.branches:
            if branch.match(event.branch):
                matches_branch = True
        if self.branches and not matches_branch:
            return FalseWithReason("Branches %s doesn't match %s" % (
                self.branches, event.branch))

        matches_ref = False
        if event.ref is not None:
            for ref in self.refs:
                if ref.match(event.ref):
                    matches_ref = True
                    break
        if self.refs and not matches_ref:
            return FalseWithReason(
                "Refs %s doesn't match %s" % (self.refs, event.ref))

        matches_branch = False
        if event.branch is not None:
            for ref in self.branches:
                if ref.match(event.branch):
                    matches_branch = True
                    break
        if self.branches and not matches_branch:
            return FalseWithReason("Branches %s doesn't match %s" % (
                self.branches, event.branch))

        matches_comment_re = False
        for comment_re in self.comments:
            if event.comment is not None and comment_re.search(event.comment):
                matches_comment_re = True
                break
        if self.comments and not matches_comment_re:
            return FalseWithReason("Comments %s doesn't match %s" % (
                self.comments, event.comment))

        return True


class BitbucketCloudTriggerEvent(TriggerEvent):
    def __init__(self):
        super(BitbucketCloudTriggerEvent, self).__init__()
        self.title = None
        self.action = None
        self.delivery = None
        self.check_runs = None

    def _repr(self):
        r = [super(BitbucketCloudTriggerEvent, self)._repr()]
        if self.action:
            r.append(self.action)
        if self.canonical_project_name:
            r.append(self.canonical_project_name)
        if self.change_number:
            r.append('%s,%s' % (self.change_number, self.patch_number))
        if self.delivery:
            r.append('delivery: %s' % self.delivery)
        if self.check_runs:
            r.append('check_runs: %s' % self.check_runs)
        return ' '.join(r)
