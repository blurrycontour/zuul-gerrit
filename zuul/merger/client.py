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
from uuid import uuid4

from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.model import (
    MergeRequest, MergeRequestType, PRECEDENCE_HIGH, PRECEDENCE_NORMAL
)
from zuul.zk.merger import MergerApi


class MergeClient(object):
    log = logging.getLogger("zuul.MergeClient")

    _merger_api_class = MergerApi

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        self.git_timeout = get_default(
            self.config, 'merger', 'git_timeout', 300)
        self.merger_api = self._merger_api_class(self.sched.zk_client)

    def submitJob(
        self,
        job_type,
        data,
        build_set,
        precedence=PRECEDENCE_NORMAL,
        needs_result=False,
        event=None,
    ):
        # Extend the job data with the event id if provided
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None
        data["zuul_event_id"] = zuul_event_id

        # We need the tenant, pipeline and queue names to put the merge result
        # in the correct queue. The only source for those values in this
        # context is the buildset. If no buildset is provided, we can't provide
        # a result event. In those cases a user of this function can fall back
        # to the return value which provides the result as a future stored in a
        # ZooKeeper path.
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

        merge_request = MergeRequest(
            uuid,
            self.merger_api.initial_state,
            job_type,
            data,
            precedence,
            build_set_uuid,
            tenant_name,
            pipeline_name,
            queue_name,
        )

        log = get_annotated_logger(self.log, event)
        log.debug("Submitting job %s with data %s", merge_request, data)

        return self.merger_api.submit(merge_request, needs_result, event)

    def mergeChanges(self, items, build_set, files=None, dirs=None,
                     repo_state=None, precedence=PRECEDENCE_NORMAL,
                     branches=None, event=None):
        data = dict(items=items,
                    files=files,
                    dirs=dirs,
                    repo_state=repo_state,
                    branches=branches)
        self.submitJob(
            MergeRequestType.MERGE, data, build_set, precedence, event=event
        )

    def getRepoState(self, items, build_set,
                     precedence=PRECEDENCE_NORMAL,
                     branches=None, event=None):
        data = dict(items=items, branches=branches)
        self.submitJob(
            MergeRequestType.REF_STATE,
            data,
            build_set,
            precedence,
            event=event,
        )

    def getFiles(self, connection_name, project_name, branch, files, dirs=[],
                 precedence=PRECEDENCE_HIGH, event=None):
        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    files=files,
                    dirs=dirs)
        job = self.submitJob(
            MergeRequestType.CAT,
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
            MergeRequestType.FILES_CHANGES,
            data,
            build_set,
            precedence,
            needs_result=True,
            event=event,
        )
        return job
