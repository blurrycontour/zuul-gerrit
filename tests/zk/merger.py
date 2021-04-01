
# Copyright 2021 BMW Group
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

import logging

from zuul.model import MergeRequestState
from zuul.zk.merger import MergerApi


class TestMergerApi(MergerApi):
    log = logging.getLogger("zuul.test.zk.TestMergerApi")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hold_in_queue = False
        self.history = {}

    @property
    def initial_state(self):
        if self.hold_in_queue:
            return MergeRequestState.HOLD
        return MergeRequestState.REQUESTED

    def submit(self, merge_request, needs_result=False, event=None):
        self.log.debug("Appending merge job to history: %s", merge_request)
        self.history[merge_request.uuid] = merge_request
        return super().submit(merge_request, needs_result, event)

    def _iterMergeRequests(self):
        # As this class is mainly used for assertions in the tests, it should
        # look up the merge requests directly form ZooKeeper and not from a
        # cache layer.
        for uuid in self.kazoo_client.get_children(self.MERGE_REQUEST_ROOT):
            merge_request = self.get("/".join([self.MERGE_REQUEST_ROOT, uuid]))
            # Do not yield NoneType merge requests
            if merge_request:
                yield merge_request

    def release(self, merge_request=None):
        # Either release all jobs in HOLD state or the one specified.
        if merge_request is not None:
            merge_request.state = MergeRequestState.REQUESTED
            self.update(merge_request)
            return

        for merge_request in self.inState(MergeRequestState.HOLD):
            merge_request.state = MergeRequestState.REQUESTED
            self.update(merge_request)

    def queued(self):
        return self.inState(
            MergeRequestState.REQUESTED, MergeRequestState.HOLD
        )

    def all(self):
        return self.inState()
