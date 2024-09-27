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
from unittest import mock

from zuul import model
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.locks import pipeline_lock

import responses
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
    debian_return_data = {
        'zuul': {
            'artifacts': [
                {
                    'name': 'raw image',
                    'url': 'http://example.com/image.raw',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'debian-local',
                        'format': 'raw',
                    }
                }, {
                    'name': 'qcow2 image',
                    'url': 'http://example.com/image.qcow2',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'debian-local',
                        'format': 'qcow2',
                    }
                },
            ]
        }
    }
    ubuntu_return_data = {
        'zuul': {
            'artifacts': [
                {
                    'name': 'raw image',
                    'url': 'http://example.com/image.raw',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'ubuntu-local',
                        'format': 'raw',
                    }
                }, {
                    'name': 'qcow2 image',
                    'url': 'http://example.com/image.qcow2',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'ubuntu-local',
                        'format': 'qcow2',
                    }
                },
            ]
        }
    }

    def setUp(self):
        self.mock_aws.start()

        self.responses = responses.RequestsMock()
        self.responses.start()
        self.responses.add_passthru("http://localhost")
        self.responses.add(
            responses.GET,
            'http://example.com/image.raw',
            body="test raw image")
        self.responses.add(
            responses.GET,
            'http://example.com/image.qcow2',
            body="test qcow2 image")
        super().setUp()

    def tearDown(self):
        self.mock_aws.stop()
        super().tearDown()

    @simple_layout('layouts/nodepool-image.yaml', enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    @return_data(
        'build-ubuntu-local-image',
        'refs/heads/master',
        ubuntu_return_data,
    )
    @mock.patch('zuul.driver.aws.awsendpoint.AwsProviderEndpoint.uploadImage',
                return_value="test_external_id")
    def test_launcher_missing_image_build(self, mock_uploadimage):
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
            dict(name='build-ubuntu-local-image', result='SUCCESS'),
        ], ordered=False)
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
            dict(name='build-ubuntu-local-image', result='SUCCESS'),
        ], ordered=False)
        for name in [
                'review.example.com%2Forg%2Fcommon-config/debian-local',
                'review.example.com%2Forg%2Fcommon-config/ubuntu-local',
        ]:
            artifacts = self.launcher.image_build_registry.\
                getArtifactsForImage(name)
            self.assertEqual(2, len(artifacts))
            self.assertEqual('qcow2', artifacts[0].format)
            self.assertEqual('raw', artifacts[1].format)
            self.assertTrue(artifacts[0].validated)
            self.assertTrue(artifacts[1].validated)
            uploads = self.launcher.image_upload_registry.getUploadsForImage(
                name)
            self.assertEqual(1, len(uploads))
            self.assertEqual(artifacts[1].uuid, uploads[0].artifact_uuid)
            self.assertEqual("test_external_id", uploads[0].external_id)
            self.assertTrue(uploads[0].validated)

    @simple_layout('layouts/nodepool-image-no-validate.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    @mock.patch('zuul.driver.aws.awsendpoint.AwsProviderEndpoint.uploadImage',
                return_value="test_external_id")
    def test_launcher_image_no_validation(self, mock_uploadimage):
        # Test a two-stage image-build where we don't actually run the
        # validate stage (so all artifacts should be un-validated).
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
        name = 'review.example.com%2Forg%2Fcommon-config/debian-local'
        artifacts = self.launcher.image_build_registry.getArtifactsForImage(
            name)
        self.assertEqual(2, len(artifacts))
        self.assertEqual('qcow2', artifacts[0].format)
        self.assertEqual('raw', artifacts[1].format)
        self.assertFalse(artifacts[0].validated)
        self.assertFalse(artifacts[1].validated)
        uploads = self.launcher.image_upload_registry.getUploadsForImage(
            name)
        self.assertEqual(1, len(uploads))
        self.assertEqual(artifacts[1].uuid, uploads[0].artifact_uuid)
        self.assertEqual("test_external_id", uploads[0].external_id)
        self.assertFalse(uploads[0].validated)

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


class TestLauncherImagePermissions(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    tenant_config_file = 'config/launcher-config-error/main.yaml'
    mock_aws = mock_aws()

    def test_image_permissions(self):
        self.waitUntilSettled()
        self.assertHistory([])

        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")
        errors = tenant.layout.loading_errors
        self.assertEqual(len(errors), 1)
        self.assertIn('The image build job', errors[0].error)
