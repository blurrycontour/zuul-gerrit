# Copyright 2014 OpenStack Foundation
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
import threading
from typing import Any, Dict, Optional, List, Set, TYPE_CHECKING, Tuple
from uuid import uuid4

from kazoo.recipe.cache import TreeEvent

import zuul.model
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.model import PRIORITY_MAP, BuildSet, QueueItem, TriggerEvent
from zuul.zk import ZooKeeperClient
from zuul.zk.cache import ZooKeeperWorkItem
from zuul.zk.client import event_type_str
if TYPE_CHECKING:
    from zuul.zk.work import ZooKeeperWork


class MergeClient(object):
    log = logging.getLogger("zuul.MergeClient")

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        self.zk_client: ZooKeeperClient = self.sched.zk_client
        self.zk_work: ZooKeeperWork = self.sched.zk_work
        self.zk_work.registerAllZones()
        self.git_timeout = get_default(
            self.config, 'merger', 'git_timeout', 300)
        self.work_items: Set[str] = set()
        self.build_sets: Dict[str, BuildSet] = {}
        self._wait_events: Dict[str, threading.Event] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
        self.zk_work.registerCacheListener(self._treeCacheListener)

    def _treeCacheListener(self, segments: List[str], event: TreeEvent,
                           item: Optional[ZooKeeperWorkItem]) -> None:

        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED)\
                and item\
                and item.path in self.work_items:

            log = get_annotated_logger(self.log, None,
                                       build=item.content['uuid'])
            log.debug("TreeEvent (%s) [%s]: %s", event_type_str(event),
                      segments, item)
            if len(segments) == 2 and segments[1] == 'result':
                self.onBuildCompleted(item)
            elif len(segments) == 2 and segments[1] == 'exception':
                self.onBuildCompleted(item)

    def stop(self):
        pass

    def areMergesOutstanding(self):
        if self.work_items:
            return True
        return False

    def submitJob(self, name: str, data: Dict[str, Any],
                  build_set: Optional[BuildSet],
                  precedence: int = zuul.model.PRECEDENCE_NORMAL, event=None)\
            -> Tuple[str, str]:
        log = get_annotated_logger(self.log, event)
        uuid = str(uuid4().hex)
        log.debug("Submitting job %s with data %s", uuid, data)
        self._wait_events[uuid] = threading.Event()
        node = self.zk_work.submit(uuid=uuid, name=name, params=data,
                                   zone=self.zk_work.DEFAULT_ZONE,
                                   precedence=PRIORITY_MAP[precedence])
        if build_set:
            self.build_sets[node] = build_set
        self.work_items.add(node)
        return node, uuid

    def mergeChanges(self, items: List[QueueItem], build_set: BuildSet,
                     files: Optional[List[str]] = None,
                     dirs: Optional[List[str]] = None,
                     repo_state: Optional[Dict[str, Any]] = None,
                     precedence: int = zuul.model.PRECEDENCE_NORMAL,
                     branches: Optional[List[str]] = None,
                     event: Optional[TriggerEvent] = None) -> None:
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None
        data = dict(items=items,
                    files=files,
                    dirs=dirs,
                    repo_state=repo_state,
                    branches=branches,
                    zuul_event_id=zuul_event_id)
        self.submitJob('merger:merge', data, build_set, precedence,
                       event=event)

    def getRepoState(self, items: List[QueueItem], build_set: BuildSet,
                     precedence: int = zuul.model.PRECEDENCE_NORMAL,
                     branches: Optional[List[str]] = None,
                     event: Optional[TriggerEvent] = None) -> None:
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(items=items, branches=branches,
                    zuul_event_id=zuul_event_id)
        self.submitJob('merger:refstate', data, build_set, precedence,
                       event=event)

    def getFiles(self, connection_name: str, project_name: str, branch: str,
                 files: Optional[List[str]], dirs: Optional[List[str]] = None,
                 precedence: int = zuul.model.PRECEDENCE_HIGH,
                 event: Optional[TriggerEvent] = None) -> Tuple[str, str]:
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    files=files,
                    dirs=dirs or [],
                    zuul_event_id=zuul_event_id)
        return self.submitJob('merger:cat', data, None, precedence,
                              event=event)

    def getFilesChanges(self, connection_name: str, project_name: str,
                        branch: str, tosha=None,
                        precedence: int = zuul.model.PRECEDENCE_HIGH,
                        build_set: Optional[BuildSet] = None,
                        event: Optional[TriggerEvent] = None)\
            -> Tuple[str, str]:
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    tosha=tosha,
                    zuul_event_id=zuul_event_id)
        return self.submitJob('merger:fileschanges', data, build_set,
                              precedence, event=event)

    def waitFor(self, unique: str, timeout: float = 300):
        if unique in self._wait_events:
            self._wait_events[unique].wait(timeout)

    def onBuildCompleted(self, work_item: ZooKeeperWorkItem):
        result = {}
        zuul_event_id = work_item.result.get('zuul_event_id')\
            if work_item.result else None
        log = get_annotated_logger(self.log, zuul_event_id)

        merged = work_item.result.get('merged', False)
        result['updated'] = work_item.result.get('updated', False)
        commit = work_item.result.get('commit')
        files = work_item.result.get('files', {})
        repo_state = work_item.result.get('repo_state', {})
        item_in_branches = work_item.result.get('item_in_branches', [])
        result['files'] = files
        self.results[work_item.path] = result
        log.info("Merge %s complete, merged: %s, updated: %s, "
                 "commit: %s, branches: %s", work_item.path, merged,
                 result['updated'], commit, item_in_branches)
        if work_item.path in self.build_sets:
            if work_item.content['name'] == 'merger:fileschanges':
                self.sched.onFilesChangesCompleted(
                    self.build_sets[work_item.path], files)
            else:
                self.sched.onMergeCompleted(self.build_sets[work_item.path],
                                            merged, result['updated'], commit,
                                            files, repo_state,
                                            item_in_branches)
        # TODO JK: del self.build_sets[work_item.path]
        # The test suite expects the job to be removed from the
        # internal account after the wake flag is set.
        self.zk_work.remove(work_item.path)
        unique = work_item.content['uuid']
        if unique in self._wait_events:
            self._wait_events[unique].set()
            del self._wait_events[unique]
        self.work_items.remove(work_item.path)
