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
            zuul_event_id=None,
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

    # def test_multi_launcher(self):
    #     self.create_launchers(
    #         count=5, providers=["region-1", "region-2", "region-3"])

    #     requests = []
    #     for i in range(50):
    #         labels = ["foo", "bar"]
    #         request = model.NodesetRequest(labels)
    #         self.client.submit(request)
    #         requests.append(request)

    #     for _ in iterate_timeout(30, "request to be fulfilled"):
    #         for r in requests:
    #             self.client.refresh(r)
    #         if all(r.state == model.NodesetRequest.STATE_FULFILLED
    #                for r in requests):
    #             break
    #         time.sleep(1)

    # def test_launcher_failover(self):
    #     launcher = FakeLauncher(
    #         "fake-launcher", self.zk_client, self.component_registry,
    #         providers=["stratocumulus"])
    #     launcher.hold_nodes_in_build = True
    #     try:
    #         launcher.start()

    #         labels = ["foo", "bar"]
    #         nodeset_request = model.NodesetRequest(labels)
    #         self.client.submit(nodeset_request)

    #         for _ in iterate_timeout(10, "request to be accepted"):
    #             self.client.refresh(nodeset_request)
    #             if (nodeset_request.state
    #                     == model.NodesetRequest.STATE_ACCEPTED):
    #                 break
    #             time.sleep(0.1)

    #         requests = launcher.api.getNodesetRequests()
    #         nodes = launcher.api.getProviderNodes()
    #     finally:
    #         launcher.stop()

    #     # We need to unlock all nodes and requests as we are using the
    #     # same ZK client, so the locks are still valid.
    #     for node in nodes:
    #         if node.lock:
    #             launcher.api.unlockNode(node)
    #     for request in requests:
    #         if request.lock:
    #             launcher.api.unlockRequest(request)

    #     self.create_launchers(count=1, start_index=1)
    #     for _ in iterate_timeout(30, "request to be fulfilled"):
    #         self.client.refresh(nodeset_request)
    #         if nodeset_request.state == model.NodesetRequest.STATE_FULFILLED:
    #             break
    #         time.sleep(0.1)
