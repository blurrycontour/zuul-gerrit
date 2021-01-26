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

import json
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

import gear

from zuul.lib.config import get_default
from zuul.model import BuildSet, PRECEDENCE_HIGH, PRECEDENCE_NORMAL
from zuul.zk.merges import MergeJob, MergeJobQueue, MergeJobType


def getJobData(job):
    if not len(job.data):
        return {}
    d = job.data[-1]
    if not d:
        return {}
    return json.loads(d)


class MergeGearmanClient(gear.Client):
    def __init__(self, merge_client):
        super(MergeGearmanClient, self).__init__('Zuul Merge Client')
        self.__merge_client = merge_client

    def handleWorkComplete(self, packet):
        job = super(MergeGearmanClient, self).handleWorkComplete(packet)
        self.__merge_client.onBuildCompleted(job)
        return job

    def handleWorkFail(self, packet):
        job = super(MergeGearmanClient, self).handleWorkFail(packet)
        self.__merge_client.onBuildCompleted(job)
        return job

    def handleWorkException(self, packet):
        job = super(MergeGearmanClient, self).handleWorkException(packet)
        self.__merge_client.onBuildCompleted(job)
        return job

    def handleDisconnect(self, job):
        job = super(MergeGearmanClient, self).handleDisconnect(job)
        self.__merge_client.onBuildCompleted(job)


class MergeClient(object):
    log = logging.getLogger("zuul.MergeClient")

    _merge_job_queue_class = MergeJobQueue

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        server = self.config.get('gearman', 'server')
        port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        self.log.debug("Connecting to gearman at %s:%s" % (server, port))
        self.gearman = MergeGearmanClient(self)
        self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca,
                               keepalive=True, tcp_keepidle=60,
                               tcp_keepintvl=30, tcp_keepcnt=5)
        self.git_timeout = get_default(
            self.config, 'merger', 'git_timeout', 300)
        self.log.debug("Waiting for gearman")
        self.gearman.waitForServer()
        self.jobs = set()

        self.merge_job_queue = self._merge_job_queue_class(
            self.sched.zk_client
        )

    def stop(self):
        self.gearman.shutdown()

    def areMergesOutstanding(self):
        if self.jobs:
            return True
        return False

    def submitJob(
        self,
        job_type: MergeJobType,
        data: Dict[str, Any],
        build_set: Optional[BuildSet],
        precedence: int = PRECEDENCE_NORMAL,
        needs_result: bool = False,
        event=None,
    ):
        # Extend the job data with the event id if provided
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None
        data["zuul_event_id"] = zuul_event_id

        # In case no build_set is provided, we don't have the necessary values
        # in the MergeJob to provide a result event. However, this shouldn't be
        # much of a problem, as in those cases, the return value of this
        # function will be used to provide the result.
        build_set_uuid = None
        tenant_name = None
        pipeline_name = None
        queue_name = None

        if build_set is not None:
            build_set_uuid = build_set.uuid
            tenant_name = build_set.item.pipeline.tenant.name
            pipeline_name = build_set.item.pipeline.name
            queue_name = build_set.item.queue.name

        uuid = str(uuid4().hex)

        job = MergeJob(
            uuid,
            self.merge_job_queue.initial_state,
            job_type,
            data,
            precedence,
            build_set_uuid,
            tenant_name,
            pipeline_name,
            queue_name,
        )

        return self.merge_job_queue.submit(job, needs_result, event)

    def mergeChanges(self, items, build_set, files=None, dirs=None,
                     repo_state=None, precedence=PRECEDENCE_NORMAL,
                     branches=None, event=None):
        data = dict(items=items,
                    files=files,
                    dirs=dirs,
                    repo_state=repo_state,
                    branches=branches)

        self.submitJob(
            MergeJobType.MERGE, data, build_set, precedence, event=event
        )

    def getRepoState(self, items, build_set,
                     precedence=PRECEDENCE_NORMAL,
                     branches=None, event=None):

        data = dict(items=items, branches=branches)
        self.submitJob(
            MergeJobType.REF_STATE, data, build_set, precedence, event=event
        )

    def getFiles(self, connection_name, project_name, branch, files, dirs=[],
                 precedence=PRECEDENCE_HIGH, event=None):
        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    files=files,
                    dirs=dirs)
        job = self.submitJob(
            MergeJobType.CAT,
            data,
            None,
            precedence,
            needs_result=True,
            event=event,
        )
        return job

    def getFilesChanges(self, connection_name, project_name, branch,
                        tosha=None, precedence=PRECEDENCE_HIGH,
                        build_set=None, event=None):

        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    tosha=tosha)
        job = self.submitJob(
            MergeJobType.FILES_CHANGES,
            data,
            build_set,
            precedence,
            needs_result=True,
            event=event,
        )
        return job
