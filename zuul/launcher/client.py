# Copyright 2024 BMW Group
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

from zuul.model import NodesetRequest
from zuul.lib import tracing
from zuul.lib.logutil import get_annotated_logger

from opentelemetry import trace


class LauncherClient:
    log = logging.getLogger("zuul.LauncherClient")
    tracer = trace.get_tracer("zuul")

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched

    def requestNodeset(self, item, job, priority):
        log = get_annotated_logger(self.log, item.event)
        labels = [n.label for n in job.nodeset.getNodes()]

        buildset = item.current_build_set
        parent_span = tracing.restoreSpan(buildset.span_info)
        request_time = time.time()
        with trace.use_span(parent_span):
            request_span = self.tracer.start_span(
                "NodesetRequest", start_time=request_time)
        span_info = tracing.getSpanInfo(request_span)

        with self.sched.createZKContext(None, self.log) as ctx:
            state = (NodesetRequest.State.REQUESTED if job.nodeset.nodes
                     else NodesetRequest.State.FULFILLED)
            request = NodesetRequest.new(
                ctx,
                state=state,
                tenant_name=item.pipeline.tenant.name,
                pipeline_name=item.pipeline.name,
                buildset_uuid=buildset.uuid,
                job_uuid=job.uuid,
                job_name=job.name,
                labels=labels,
                priority=priority,
                # relative_priority,
                request_time=request_time,
                zuul_event_id=item.event.zuul_event_id,
                span_info=span_info,
            )
            log.info("Submitted nodeset request %s", request)
