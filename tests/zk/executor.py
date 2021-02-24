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
import re
from typing import Union

from kazoo.exceptions import NoNodeError

from zuul.model import BuildRequest, BuildRequestState
from zuul.zk.executor import ExecutorApi


class TestExecutorApi(ExecutorApi):
    log = logging.getLogger("zuul.test.zk.TestExecutorApi")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hold_in_queue = False

    @property
    def initial_state(self) -> BuildRequestState:
        if self.hold_in_queue:
            return BuildRequestState.HOLD
        return BuildRequestState.REQUESTED

    def _iterBuildRequests(self):
        # As this class is mainly used for assertions in the tests, it should
        # look up the build requests directly from ZooKeeper and not from a
        # cache layer.
        zones = []
        if self.zone_filter:
            zones = self.zone_filter
        else:
            try:
                # Get all available zones from ZooKeeper
                zones = self.kazoo_client.get_children(self.BUILD_REQUEST_ROOT)
            except NoNodeError:
                return

        for zone in zones:
            try:
                zone_path = "/".join([self.BUILD_REQUEST_ROOT, zone])
                builds = self.kazoo_client.get_children(zone_path)
            except NoNodeError:
                # Skip this zone as it doesn't have any builds
                continue

            for uuid in builds:
                build = self.get("/".join([zone_path, uuid]))
                # Do not yield NoneType builds
                if build:
                    yield build

    def release(self, what: Union[None, str, BuildRequest] = None):
        """
        Releases a build request which was previously put on hold for testing.

        The what parameter specifies what to release. This can be a concrete
        build request or a regular expression matching a job name.
        """
        self.log.debug("Releasing builds matching %s", what)
        if isinstance(what, BuildRequest):
            self.log.debug("Releasing build %s", what)
            what.state = BuildRequestState.REQUESTED
            self.update(what)
            return

        for build_request in self.inState(BuildRequestState.HOLD):
            # Either release all build requests in HOLD state or the ones
            # matching the given job name pattern.
            if what is None or re.match(what, build_request.params["job"]):
                self.log.debug("Releasing build %s", build_request)
                build_request.state = BuildRequestState.REQUESTED
                self.update(build_request)

    def queued(self):
        return self.inState(
            BuildRequestState.REQUESTED, BuildRequestState.HOLD
        )

    def all(self):
        return self.inState()
