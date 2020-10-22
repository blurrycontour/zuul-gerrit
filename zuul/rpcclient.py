# Copyright 2013 OpenStack Foundation
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
import time
from copy import deepcopy
from threading import Event
from typing import Any, Dict, Optional, List

from kazoo.recipe.cache import TreeEvent

from zuul.zk.cache import ZooKeeperWorkItem, WorkState
from zuul.zk.work import ZooKeeperWork


class RPCFailure(Exception):
    pass


class RPCClient(object):
    log = logging.getLogger("zuul.RPCClient")

    def __init__(self, zk_work: ZooKeeperWork):
        """
        Constructor
        :param zk_work: ZooKeeper work module
        """
        self._work_item_events: Dict[str, Event] = {}
        self.zk_work: ZooKeeperWork = zk_work
        self.zk_work.registerCacheListener(self._treeCacheListener)

    def _treeCacheListener(self, segments: List[str], event: TreeEvent,
                           item: Optional[ZooKeeperWorkItem]) -> None:

        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED)\
                and item\
                and item.path in self._work_item_events\
                and len(segments) == 2 \
                and segments[1] in ['result', 'exception']:
            self._work_item_events[item.path].set()
            del self._work_item_events[item.path]

    def submitJob(self, name: str, data: Dict[str, Any]) -> ZooKeeperWorkItem:
        self.log.debug("Submitting job %s with data %s" % (name, data))
        work_node = self.zk_work.submit(uuid=(str(time.time())), name=name,
                                        params=data)

        self.log.debug("Waiting for job completion")
        self._work_item_events[work_node] = Event()
        self._work_item_events[work_node].wait()
        cached = deepcopy(self.zk_work.getCached(work_node))
        try:
            if not cached or cached.state == WorkState.FAILED:
                raise RPCFailure(str(cached.exception if cached else None))
            self.log.debug("Job complete, success: %s",
                           cached.state != WorkState.FAILED)
            return cached
        finally:
            self.zk_work.remove(work_node)

    def autohold(self, tenant, project, job, change, ref, reason, count,
                 node_hold_expiration=None):
        data = {'tenant': tenant,
                'project': project,
                'job': job,
                'change': change,
                'ref': ref,
                'reason': reason,
                'count': count,
                'node_hold_expiration': node_hold_expiration}
        return self.submitJob('zuul:autohold', data).state != WorkState.FAILED

    def autohold_delete(self, request_id):
        data = {'request_id': request_id}
        return self.submitJob('zuul:autohold_delete', data)\
                   .state != WorkState.FAILED

    def autohold_info(self, request_id):
        data = {'request_id': request_id}
        work_item = self.submitJob('zuul:autohold_info', data)
        if work_item.state == WorkState.FAILED:
            return False
        else:
            return work_item.result

    # todo allow filtering per tenant, like in the REST API
    def autohold_list(self, *args, **kwargs):
        data = {}
        work_item = self.submitJob('zuul:autohold_list', data)
        if work_item.state == WorkState.FAILED:
            return False
        else:
            return work_item.result

    def enqueue(self, tenant: str, pipeline: str, project: str,
                trigger: Optional[str], change: str) -> bool:
        if trigger is not None:
            self.log.info('enqueue: the "trigger" argument is deprecated')
        data = {'tenant': tenant,
                'pipeline': pipeline,
                'project': project,
                'trigger': trigger,
                'change': change,
                }
        return self.submitJob('zuul:enqueue', data).state != WorkState.FAILED

    def enqueue_ref(
            self, tenant, pipeline, project, trigger, ref, oldrev, newrev):
        if trigger is not None:
            self.log.info('enqueue_ref: the "trigger" argument is deprecated')
        data = {'tenant': tenant,
                'pipeline': pipeline,
                'project': project,
                'trigger': trigger,
                'ref': ref,
                'oldrev': oldrev,
                'newrev': newrev,
                }
        return self.submitJob('zuul:enqueue_ref', data)\
                   .state != WorkState.FAILED

    def dequeue(self, tenant, pipeline, project, change, ref):
        data = {'tenant': tenant,
                'pipeline': pipeline,
                'project': project,
                'change': change,
                'ref': ref,
                }
        return self.submitJob('zuul:dequeue', data).state != WorkState.FAILED

    def promote(self, tenant, pipeline, change_ids):
        data = {'tenant': tenant,
                'pipeline': pipeline,
                'change_ids': change_ids,
                }
        return self.submitJob('zuul:promote', data).state != WorkState.FAILED

    def get_running_jobs(self):
        data = {}
        work_item = self.submitJob('zuul:get_running_jobs', data)
        if work_item.state == WorkState.FAILED:
            return False
        else:
            return work_item.result

    def shutdown(self):
        # self.gearman.shutdown()
        pass

    def get_job_log_stream_address(self, uuid, logfile='console.log'):
        data = {'uuid': uuid, 'logfile': logfile}
        work_item = self.submitJob('zuul:get_job_log_stream_address', data)
        if work_item.state == WorkState.FAILED:
            return False
        else:
            return work_item.result
