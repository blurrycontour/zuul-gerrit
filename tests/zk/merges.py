# Copyright 2020 BMW Group
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
from typing import Optional

from zuul.zk import ZooKeeperClient
from zuul.zk.event_queues import MergerEventResultFuture
from zuul.zk.merges import MergeJob, MergeJobQueue, MergeJobState


class TestMergeJobQueue(MergeJobQueue):

    log = logging.getLogger("zuul.test.zk.TestMergeJobQueue")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self.hold_in_queue: bool = False
        self.history = {}

    @property
    def initial_state(self) -> MergeJobState:
        if self.hold_in_queue:
            return MergeJobState.HOLD
        return MergeJobState.REQUESTED

    def submit(
        self, job: MergeJob, needs_result: bool = False, event=None
    ) -> Optional[MergerEventResultFuture]:
        self.log.debug("Appending merge job to history: %s", job)
        self.history[job.uuid] = job
        return super().submit(job, needs_result, event)

    def all(self):
        return self.in_state()

    def queued(self):
        return self.in_state(MergeJobState.HOLD)

    def release(self, job: Optional[MergeJob] = None):
        # Either release all jobs in HOLD state or the one specified.
        if job is not None:
            job.state = MergeJobState.REQUESTED
            self.update(job)
            return

        for job in self.in_state(MergeJobState.HOLD):
            job.state = MergeJobState.REQUESTED
            self.update(job)
