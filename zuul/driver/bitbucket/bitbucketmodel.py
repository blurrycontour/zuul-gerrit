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

from zuul.model import Change, TriggerEvent, EventFilter


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
        return isinstance(obj, PullRequest) and self.project == obj.project \
            and self.id == obj.id and self.updatedDate == obj.updatedDate

    def isUpdateOf(self, other):
        if (self.project == other.project and
                hasattr(other, 'id') and self.id == other.id and
                hasattr(other, 'patchset') and
                self.patchset != other.patchset and
                hasattr(other, 'updatedDate') and
                self.updatedDate > other.updatedDate):
            return True
        return False


class BitbucketTriggerEvent(TriggerEvent):
    def __init__(self):
        super(BitbucketTriggerEvent, self).__init__()
        self.trigger_name = 'bitbucket'
        self.title = None
        self.action = None
        self.status = None


# taken almost verbatimly from PagureEventFilter
class BitbucketEventFilter(EventFilter):
    def __init__(self, trigger, types=[], refs=[], statuses=[],
                 comments=[], actions=[]):

        EventFilter.__init__(self, trigger)

        self._types = types
        self._refs = refs
        self._comments = comments
        self.types = [re2.compile(x) for x in types]
        self.refs = [re2.compile(x) for x in refs]
        self.comments = [re2.compile(x) for x in comments]
        self.actions = actions
        self.statuses = statuses

    def matches(self, event, change):
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return False

        matches_ref = False
        if event.ref is not None:
            for ref in self.refs:
                if ref.match(event.ref):
                    matches_ref = True
        if self.refs and not matches_ref:
            return False

        matches_comment_re = False
        for comment_re in self.comments:
            if (event.comment is not None and
                    comment_re.search(event.comment)):
                matches_comment_re = True
        if self.comments and not matches_comment_re:
            return False

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return False

        matches_status = False
        for status in self.statuses:
            if event.status == status:
                matches_status = True
        if self.statuses and not matches_status:
            return False

        return True
