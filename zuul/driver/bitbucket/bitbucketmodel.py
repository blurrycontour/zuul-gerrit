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

import re2

from zuul.model import Change, EventFilter, TriggerEvent, RefFilter


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.pr = None
        self.updatedDate = None
        self.title = None
        self.reviews = []
        self.files = []
        self.labels = []

    def __eq__(self, obj):
        return (isinstance(obj, PullRequest) and
                self.project == obj.project and
                self.id == obj.id and
                self.updatedDate == obj.updatedDate)

    def isUpdateOf(self, other):
        if (self.project == other.project and
            hasattr(other, 'id') and
            self.id == other.id and
            hasattr(other, 'patchset') and
            self.patchset != other.patchset and
            hasattr(other, 'updatedDate') and
            self.updatedDate > other.updatedDate
        ):
            return True
        return False


class BitbucketTriggerEvent(TriggerEvent):
    def __init__(self):
        super(BitbucketTriggerEvent, self).__init__()
        self.trigger_name = 'bitbucket'
        self.title = None
        self.action = None
        self.status = None


# taken almost verbatimly from PagureRefFilter
class BitbucketChangeFilter(RefFilter):
    def __init__(self, connection_name, open=None,
                 closed=None, status=None, canMerge=None):
        RefFilter.__init__(self, connection_name)
        self.open = open
        self.closed = closed
        self.status = status
        self.canMerge = canMerge

    def __repr__(self):
        ret = '<BitbucketChangeFilter connection_name: {} '.format(self.connection_name)
        if self.open:
            ret += ' open: {}'.format(self.open)
        if self.closed:
            ret += ' closed: {}'.format(self.closed)
        if self.status:
            ret += ' status: {}'.format(self.status)
        if self.canMerge:
            ret += ' canMerge: {}'.format(self.status)

        ret += '>'
        return ret

    def matches(self, change):
        if self.open:
            if change.open != self.open:
                return False

        if self.closed:
            if change.closed != self.closed:
                return False

        if self.status:
            if change.status != self.status:
                return False

        if self.canMerge:
            if change.canMerge != self.canMerge:
                return False

        return True


# taken almost verbatimly from PagureEventFilter
class BitbucketEventFilter(EventFilter):
    def __init__(self, trigger, types=[], branches=[], statuses=[],
                 comments=[], actions=[]):

        EventFilter.__init__(self, trigger)

        self._types = types
        self._branches = branches
        self._comments = comments
        self.types = [re2.compile(x) for x in types]
        self.branches = [re2.compile(x) for x in branches]
        self.comments = [re2.compile(x) for x in comments]
        self.actions = actions
        self.statuses = statuses

    def matches(self, event, change):
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
                break
        if self.types and not matches_type:
            return False

        matches_branch = False
        if event.branch is not None:
            for ref in self.branches:
                if ref.match(event.branch):
                    matches_branch = True
                    break
        if self.branches and not matches_branch:
            return False

        matches_comment_re = False
        for comment_re in self.comments:
            if event.comment is not None and comment_re.search(event.comment):
                matches_comment_re = True
                break
        if self.comments and not matches_comment_re:
            return False

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
                break
        if self.actions and not matches_action:
            return False

        matches_status = False
        for status in self.statuses:
            if event.status == status:
                matches_status = True
                break
        if self.statuses and not matches_status:
            return False

        return True
