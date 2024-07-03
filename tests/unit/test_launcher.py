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
import time
import uuid

from zuul import model
from zuul.zk.event_queues import PipelineResultEventQueue

from tests.base import (
    ZuulTestCase,
    iterate_timeout
)


class TestLauncher(ZuulTestCase):

    config_file = 'zuul-connections-nodepool.conf'
    tenant_config_file = 'config/single-tenant/main.yaml'

    def test_launcher(self):
        result_queue = PipelineResultEventQueue(self.zk_client, "foo", "bar")
        labels = ["foo", "bar"]
        ctx = self.createZKContext(None)
        request = model.NodesetRequest.new(
            ctx,
            tenant_name="foo",
            pipeline_name="bar",
            buildset_uuid=uuid.uuid4().hex,
            job_uuid=uuid.uuid4().hex,
            job_name="foobar",
            labels=labels,
            priority=100,
            request_time=time.time(),
            zuul_event_id=uuid.uuid4().hex,
            span_info=None,
        )

        for _ in iterate_timeout(10, "nodeset request to be fulfilled"):
            result_events = list(result_queue)
            if result_events:
                for event in result_events:
                    # Remove event(s) from queue
                    result_queue.ack(event)
                break

        self.assertEqual(len(result_events), 1)
        for event in result_queue:
            self.assertEqual(event.request_id, request.uuid)
            self.assertEqual(event.build_set_uuid, request.buildset_uuid)

        request.delete(ctx)
        self.waitUntilSettled()
