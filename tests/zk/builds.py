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
import re
from typing import List, Optional, Union

from zuul.zk import ZooKeeperClient
from zuul.zk.builds import BuildItem, BuildQueue, BuildState, TreeCallback


class TestBuildQueue(BuildQueue):
    log = logging.getLogger("zuul.test.zk.TestBuildQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        zone_filter: Optional[List[str]] = None,
        tree_callback: Optional[TreeCallback] = None,
        use_cache: bool = False,
    ):
        super().__init__(client, zone_filter, tree_callback, use_cache)
        self.hold_in_queue: bool = False

    @property
    def initial_state(self) -> BuildState:
        if self.hold_in_queue:
            return BuildState.HOLD
        return BuildState.REQUESTED

    def requested(self):
        return self.in_state(BuildState.REQUESTED, BuildState.HOLD)

    def all(self):
        return self.in_state()

    def release(self, what: Union[None, str, BuildItem] = None):
        """
        Releases a build which was previously put on hold for testing.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if isinstance(what, BuildItem):
            what.state = BuildState.REQUESTED
            self.update(what)
            return

        for build in self.in_state(BuildState.HOLD):
            # Either release all builds in HOLD state or the ones matching
            # the given job name pattern.
            if what is None or re.match(what, build.params["job"]):
                build.state = BuildState.REQUESTED
                self.update(build)
