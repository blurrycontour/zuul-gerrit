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

import json
import logging
import re
import time
from typing import List, Optional, Union

from kazoo.recipe.cache import TreeEvent

from zuul.zk import ZooKeeperClient
from zuul.zk.builds import BuildItem, BuildState, ZooKeeperBuilds


class TestZooKeeperBuilds(ZooKeeperBuilds):
    log = logging.getLogger("zuul.test.zk.TestZooKeeperBuilds")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self.hold_in_queue: bool = False
        # TODO (felix): Is the history and the treeCacheListener needed?
        self.history: List[BuildItem] = []
        self.registerCacheListener(self._historyTreeCacheListener)

    def _historyTreeCacheListener(
        self, segments: List[str], event: TreeEvent, item: Optional[BuildItem]
    ) -> None:

        if (
            event.event_type == TreeEvent.NODE_ADDED
            and item
            and len(segments) == 1
        ):
            self.history.append(item)

    def _createNewState(self) -> BuildState:
        return BuildState.HOLD if self.hold_in_queue else BuildState.REQUESTED

    def setHoldInQueue(self, hold: bool):
        self.hold_in_queue = hold

    def release(self, what: Union[None, str, BuildItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if isinstance(what, BuildItem):
            what.state = BuildState.REQUESTED
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding="UTF-8"),
                version=what.stat.version,
            )
        else:
            for path, cached in self.inState(BuildState.HOLD):
                # Either release all builds in HOLD state or the ones matching
                # the given job name pattern.
                if not what or re.match(what, cached.content["params"]["job"]):
                    cached.state = BuildState.REQUESTED
                    self.kazoo_client.set(
                        path,
                        json.dumps(cached.content).encode(encoding="UTF-8"),
                        version=cached.stat.version,
                    )

    def waitUntilReleased(self, what: Union[None, str, BuildItem] = None):
        paths: List[str] = []
        if isinstance(what, BuildItem):
            paths = [what.path]
        else:
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    job_name = cached.content["params"]["job"]
                    if not what or re.match(what, job_name):
                        paths.append(path)

        self.log.debug("Waiting for %s to be released", paths)

        while True:
            on_hold = []
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    if path in paths and cached.state == BuildState.HOLD:
                        on_hold.append(path)
            if len(on_hold) == 0:
                self.log.debug("%s released", what)
                return
            else:
                self.log.debug("Still waiting for %s to be released", on_hold)
                time.sleep(0.1)
