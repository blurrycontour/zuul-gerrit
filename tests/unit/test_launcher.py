# Copyright 2024 Acme Gating, LLC
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
from zuul.zk.locks import pipeline_lock

from moto import mock_aws

from tests.base import (
    ZuulTestCase,
    iterate_timeout,
    simple_layout,
    return_data,
)


class TestLauncher(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    mock_aws = mock_aws()

    def setUp(self):
        self.mock_aws.start()
        super().setUp()

    def tearDown(self):
        self.mock_aws.stop()
        super().tearDown()

    @simple_layout('layouts/nodepool-image.yaml', enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        {'zuul':
         {'artifacts': [
             {'name': 'raw image',
              'url': 'http://example.com/image.raw',
              'metadata': {
                  'type': 'zuul_image',
                  'image_name': 'debian-local',
                  'format': 'raw',
              }},
             {'name': 'qcow2 image',
              'url': 'http://example.com/image.qcow2',
              'metadata': {
                  'type': 'zuul_image',
                  'image_name': 'debian-local',
                  'format': 'qcow2',
              }},
         ]}}
    )
    def test_launcher_missing_image_build(self):
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
        ])
        self.scheds.execute(lambda app: app.sched.reconfigure(app.config))

        for _ in iterate_timeout(
                30, "scheduler and launcher to have the same layout"):
            if (self.scheds.first.sched.local_layout_state.get("tenant-one") ==
                self.launcher.local_layout_state.get("tenant-one")):
                break

        # The build should not run again because the image is no
        # longer missing
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
        ])

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_launcher_missing_label(self):
        result_queue = PipelineResultEventQueue(
            self.zk_client, "tenant-one", "check")
        labels = ["debian-normal", "debian-unavailable"]

        ctx = self.createZKContext(None)
        # Lock the pipeline, so we can grab the result event
        with pipeline_lock(self.zk_client, "tenant-one", "check"):
            request = model.NodesetRequest.new(
                ctx,
                tenant_name="tenant-one",
                pipeline_name="check",
                buildset_uuid=uuid.uuid4().hex,
                job_uuid=uuid.uuid4().hex,
                job_name="foobar",
                labels=labels,
                priority=100,
                request_time=time.time(),
                zuul_event_id=uuid.uuid4().hex,
                span_info=None,
            )
            for _ in iterate_timeout(
                    10, "nodeset request to be fulfilled"):
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

        request.refresh(ctx)
        self.assertEqual(request.state, model.NodesetRequest.State.FAILED)
        self.assertEqual(len(request.provider_nodes), 0)

        request.delete(ctx)
        self.waitUntilSettled()
