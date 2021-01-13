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
from zuul.zk.builds import BuildItem, BuildQueue, BuildState, TreeCallback


class TestBuildQueue(BuildQueue):
    log = logging.getLogger("zuul.test.zk.TestBuildQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        zone_filter: Optional[List[str]] = None,
        tree_callback: Optional[TreeCallback] = None,
    ):
        super().__init__(client, zone_filter, tree_callback)
        self.hold_in_queue: bool = False

    # TODO (felix): Move those method to the production class?
    def requested(self):
        return self.in_state(BuildState.REQUESTED, BuildState.HOLD)

    def all(self):
        return self.in_state()


# TODO (felix): Remove
class TestZooKeeperBuilds:
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

    def release(self, what: Union[None, str, BuildItem] = None):
        """
        Releases a build item(s) which was previously put on hold.

        :param what: What to release, can be a concrete build item or a regular
                     expression matching job name
        """
        if isinstance(what, BuildItem):
            what.state = BuildState.REQUESTED
            what.toDict()
            self.kazoo_client.set(
                what.path,
                json.dumps(what.content).encode(encoding="UTF-8"),
                version=what.stat.version,
            )
            return

        for path, cached in self.in_state(BuildState.HOLD):
            # Either release all builds in HOLD state or the ones matching
            # the given job name pattern.
            if what is None or re.match(what, cached.params["job"]):
                cached.state = BuildState.REQUESTED
                self.build_queue.update(cached)

    # TODO (felix): What do we need this for? Can't we just use release() +
    # waitUntilSettled() in the tests?
    # TODO (felix): This thing should have a timeout, otherwise it might loop
    # endlessly.
    def waitUntilReleased(self, what: Union[None, str, BuildItem] = None):
        paths: List[str] = []
        if isinstance(what, BuildItem):
            paths = [what.path]
        else:
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    job_name = cached.params["job"]
                    if not what or re.match(what, job_name):
                        paths.append(path)

        self.log.debug("Waiting for %s to be released", paths)

        while True:
            on_hold = []
            for cache in list(self._cache.values()):
                for path, cached in list(cache.items()):
                    self.log.debug("FE: cached.state %s", cached.state)
                    # TODO (felix): Not sure from where the _cache is loaded,
                    # but it looks like the entries in there aren't serialized
                    # yet. Thus, do it in here to make the check work (for now)
                    cached.updateFromDict(cached.content)
                    if path in paths and cached.state == BuildState.HOLD:
                        on_hold.append(path)
            if not on_hold:
                self.log.debug("%s released", what)
                return
            else:
                self.log.debug("Still waiting for %s to be released", on_hold)
                time.sleep(0.1)
