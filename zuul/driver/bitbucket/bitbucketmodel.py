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

from zuul.model import Change


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.project = None
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
