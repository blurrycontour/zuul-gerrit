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

import textwrap
import time
import uuid
from collections import defaultdict
from unittest import mock, skip

from zuul import model
from zuul.launcher.client import LauncherClient
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.locks import pipeline_lock

import responses
import testtools
from kazoo.exceptions import NoNodeError
from moto import mock_aws
import boto3

from tests.base import (
    ZuulTestCase,
    iterate_timeout,
    okay_tracebacks,
    simple_layout,
    return_data,
)


class LauncherBaseTestCase(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    mock_aws = mock_aws()

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
        self.s3 = boto3.resource('s3', region_name='us-west-2')
        self.s3.create_bucket(
            Bucket='zuul',
            CreateBucketConfiguration={'LocationConstraint': 'us-west-2'})
        super().setUp()

    def tearDown(self):
        self.mock_aws.stop()
        super().tearDown()


class TestLauncher(LauncherBaseTestCase):
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
                        'sha256': ('d043e8080c82dbfeca3199a24d5f0193'
                                   'e66755b5ba62d6b60107a248996a6795'),
                        'md5sum': '78d2d3ff2463bc75c7cc1d38b8df6a6b',
                    }
                }, {
                    'name': 'qcow2 image',
                    'url': 'http://example.com/image.qcow2',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'debian-local',
                        'format': 'qcow2',
                        'sha256': ('59984dd82f51edb3777b969739a92780'
                                   'a520bb314b8d64b294d5de976bd8efb9'),
                        'md5sum': '262278e1632567a907e4604e9edd2e83',
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
                        'sha256': ('d043e8080c82dbfeca3199a24d5f0193'
                                   'e66755b5ba62d6b60107a248996a6795'),
                        'md5sum': '78d2d3ff2463bc75c7cc1d38b8df6a6b',
                    }
                }, {
                    'name': 'qcow2 image',
                    'url': 'http://example.com/image.qcow2',
                    'metadata': {
                        'type': 'zuul_image',
                        'image_name': 'ubuntu-local',
                        'format': 'qcow2',
                        'sha256': ('59984dd82f51edb3777b969739a92780'
                                   'a520bb314b8d64b294d5de976bd8efb9'),
                        'md5sum': '262278e1632567a907e4604e9edd2e83',
                    }
                },
            ]
        }
    }

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
    def test_launcher_missing_image_build(self, mock_uploadImage):
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

    @simple_layout('layouts/nodepool-image-validate.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    @mock.patch('zuul.driver.aws.awsendpoint.AwsProviderEndpoint.uploadImage',
                return_value="test_external_id")
    def test_launcher_image_validation(self, mock_uploadImage):
        # Test a two-stage image-build where we do run the validate
        # stage.
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
            dict(name='validate-debian-local-image', result='SUCCESS'),
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
            dict(name='validate-debian-local-image', result='SUCCESS'),
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
        self.assertTrue(uploads[0].validated)

    def _requestNodes(self, labels):
        result_queue = PipelineResultEventQueue(
            self.zk_client, "tenant-one", "check")

        with self.createZKContext(None) as ctx:
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
                        30, "nodeset request to be fulfilled"):
                    result_events = list(result_queue)
                    if result_events:
                        for event in result_events:
                            # Remove event(s) from queue
                            result_queue.ack(event)
                        break

            self.assertEqual(len(result_events), 1)
            for event in result_queue:
                self.assertIsInstance(event, model.NodesProvisionedEvent)
                self.assertEqual(event.request_id, request.uuid)
                self.assertEqual(event.build_set_uuid, request.buildset_uuid)

            request.refresh(ctx)
        return request

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_jobs_executed(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('check-job').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(self.getJobFromHistory('check-job').node,
                         'debian-normal')

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_launcher_failover(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)

        with mock.patch(
            'zuul.driver.aws.awsendpoint.AwsProviderEndpoint._refresh'
        ) as refresh_mock:
            # Patch 'endpoint._refresh()' to return w/o updating
            refresh_mock.side_effect = lambda o: o
            self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
            for _ in iterate_timeout(10, "node is building"):
                nodes = self.launcher.api.nodes_cache.getItems()
                if not nodes:
                    continue
                if all(
                    n.create_state and
                    n.create_state[
                        "state"] == n.create_state_machine.INSTANCE_CREATING
                    for n in nodes
                ):
                    break
            self.launcher.stop()
            self.launcher.join()

            self.launcher = self.createLauncher()

        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('check-job').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(self.getJobFromHistory('check-job').node,
                         'debian-normal')

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_launcher_missing_label(self):
        ctx = self.createZKContext(None)
        labels = ["debian-normal", "debian-unavailable"]
        request = self._requestNodes(labels)
        self.assertEqual(request.state, model.NodesetRequest.State.FAILED)
        self.assertEqual(len(request.nodes), 0)

        request.delete(ctx)
        self.waitUntilSettled()

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_node_lifecycle(self):
        nodeset = model.NodeSet()
        nodeset.addNode(model.Node("node", "debian-normal"))

        ctx = self.createZKContext(None)
        request = self._requestNodes([n.label for n in nodeset.getNodes()])

        client = LauncherClient(self.zk_client, None)
        request = client.getRequest(request.uuid)

        self.assertEqual(request.state, model.NodesetRequest.State.FULFILLED)
        self.assertEqual(len(request.nodes), 1)

        client.acceptNodeset(request, nodeset)
        self.waitUntilSettled()

        with testtools.ExpectedException(NoNodeError):
            # Request should be gone
            request.refresh(ctx)

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertIsNotNone(pnode)
            self.assertTrue(pnode.hasLock())

        client.useNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertTrue(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.IN_USE)

        client.returnNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertFalse(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.USED)

            for _ in iterate_timeout(60, "node to be deleted"):
                try:
                    pnode.refresh(ctx)
                except NoNodeError:
                    break

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_lost_nodeset_request(self):
        ctx = self.createZKContext(None)
        request = self._requestNodes(["debian-normal"])

        provider_nodes = []
        for node_id in request.nodes:
            provider_nodes.append(model.ProviderNode.fromZK(
                ctx, path=model.ProviderNode._getPath(node_id)))

        request.delete(ctx)
        self.waitUntilSettled()

        with testtools.ExpectedException(NoNodeError):
            # Request should be gone
            request.refresh(ctx)

        # TODO: in the future the nodes should be reused instead of being
        # cleaned up
        for pnode in provider_nodes:
            for _ in iterate_timeout(60, "node to be deleted"):
                try:
                    pnode.refresh(ctx)
                except NoNodeError:
                    break

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    @okay_tracebacks('_getQuotaForInstanceType')
    def test_failed_node(self):
        ctx = self.createZKContext(None)
        request = self._requestNodes(["debian-invalid"])
        self.assertEqual(request.state, model.NodesetRequest.State.FAILED)
        provider_nodes = request.provider_nodes[0]
        self.assertEqual(len(provider_nodes), 2)
        self.assertEqual(len(request.nodes), 1)
        self.assertEqual(provider_nodes[-1], request.nodes[-1])

        provider_nodes = []
        for node_id in request.nodes:
            provider_nodes.append(model.ProviderNode.fromZK(
                ctx, path=model.ProviderNode._getPath(node_id)))

        request.delete(ctx)
        self.waitUntilSettled()

        for pnode in provider_nodes:
            for _ in iterate_timeout(60, "node to be deleted"):
                try:
                    pnode.refresh(ctx)
                except NoNodeError:
                    break

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
    # Use an existing image id since the upload methods aren't
    # implemented in boto; the actualy upload process will be tested
    # in test_aws_driver.
    @mock.patch('zuul.driver.aws.awsendpoint.AwsProviderEndpoint.uploadImage',
                return_value="ami-1e749f67")
    def test_image_build_node_lifecycle(self, mock_uploadimage):
        self.waitUntilSettled()
        self.assertHistory([
            dict(name='build-debian-local-image', result='SUCCESS'),
            dict(name='build-ubuntu-local-image', result='SUCCESS'),
        ], ordered=False)

        for _ in iterate_timeout(60, "upload to complete"):
            uploads = self.launcher.image_upload_registry.getUploadsForImage(
                'review.example.com%2Forg%2Fcommon-config/debian-local')
            self.assertEqual(1, len(uploads))
            pending = [u for u in uploads if u.external_id is None]
            if not pending:
                break

        nodeset = model.NodeSet()
        nodeset.addNode(model.Node("node", "debian-local-normal"))

        ctx = self.createZKContext(None)
        request = self._requestNodes([n.label for n in nodeset.getNodes()])

        client = LauncherClient(self.zk_client, None)
        request = client.getRequest(request.uuid)

        self.assertEqual(request.state, model.NodesetRequest.State.FULFILLED)
        self.assertEqual(len(request.nodes), 1)

        client.acceptNodeset(request, nodeset)
        self.waitUntilSettled()

        with testtools.ExpectedException(NoNodeError):
            # Request should be gone
            request.refresh(ctx)

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertIsNotNone(pnode)
            self.assertTrue(pnode.hasLock())

        client.useNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertTrue(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.IN_USE)

        client.returnNodeset(nodeset)
        self.waitUntilSettled()

        for node in nodeset.getNodes():
            pnode = node._provider_node
            self.assertFalse(pnode.hasLock())
            self.assertTrue(pnode.state, pnode.State.USED)

            for _ in iterate_timeout(60, "node to be deleted"):
                try:
                    pnode.refresh(ctx)
                except NoNodeError:
                    break


class TestMinReadyLauncher(LauncherBaseTestCase):
    config_file = 'zuul-launcher-multi-region.conf'
    tenant_config_file = "config/launcher-min-ready/main.yaml"

    def _nodes_by_label(self):
        nodes = self.launcher.api.nodes_cache.getItems()
        nodes_by_label = defaultdict(list)
        for node in nodes:
            nodes_by_label[node.label].append(node)
        return nodes_by_label

    def test_min_ready(self):
        for _ in iterate_timeout(60, "nodes to be ready"):
            nodes = self.launcher.api.nodes_cache.getItems()
            # Since we are randomly picking a provider to fill the
            # min-ready slots we might end up with 3-5 nodes
            # depending on the choice of providers.
            if not 3 <= len(nodes) <= 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        self.waitUntilSettled()
        nodes = self.launcher.api.nodes_cache.getItems()
        self.assertGreaterEqual(len(nodes), 3)
        self.assertLessEqual(len(nodes), 5)

        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.waitUntilSettled()

        for _ in iterate_timeout(30, "nodes to be in-use"):
            # We expect the launcher to use the min-ready nodes
            in_use_nodes = [n for n in nodes if n.state == n.State.IN_USE]
            if len(in_use_nodes) == 2:
                break

        self.executor_server.hold_jobs_in_build = True
        self.executor_server.release()
        self.waitUntilSettled()

        check_job_a = self.getJobFromHistory('check-job', project=A.project)
        self.assertEqual(check_job_a.result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(check_job_a.node,
                         'debian-normal')

        check_job_b = self.getJobFromHistory('check-job', project=A.project)
        self.assertEqual(check_job_b.result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(check_job_b.node,
                         'debian-normal')

        # Wait for min-ready slots to be refilled
        for _ in iterate_timeout(60, "nodes to be ready"):
            nodes = self.launcher.api.nodes_cache.getItems()
            if not 3 <= len(nodes) <= 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        self.waitUntilSettled()
        nodes = self.launcher.api.nodes_cache.getItems()
        self.assertGreaterEqual(len(nodes), 3)
        self.assertLessEqual(len(nodes), 5)

    def test_max_ready_age(self):
        for _ in iterate_timeout(60, "nodes to be ready"):
            nodes = self.launcher.api.nodes_cache.getItems()
            # Since we are randomly picking a provider to fill the
            # min-ready slots we might end up with 3-5 nodes
            # depending on the choice of providers.
            if not 3 <= len(nodes) <= 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        self.waitUntilSettled()
        nodes = self.launcher.api.nodes_cache.getItems()
        self.assertGreaterEqual(len(nodes), 3)
        self.assertLessEqual(len(nodes), 5)

        nodes_by_label = self._nodes_by_label()
        self.assertEqual(1, len(nodes_by_label['debian-emea']))
        node = nodes_by_label['debian-emea'][0]

        ctx = self.createZKContext(None)
        try:
            node.acquireLock(ctx)
            node.updateAttributes(ctx, expiry_time=1)
        finally:
            node.releaseLock()

        for _ in iterate_timeout(60, "node to be cleaned up"):
            nodes = self.launcher.api.nodes_cache.getItems()
            if node in nodes:
                continue
            if not 3 <= len(nodes) <= 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        self.waitUntilSettled()
        nodes_by_label = self._nodes_by_label()
        self.assertEqual(1, len(nodes_by_label['debian-emea']))


class TestMinReadyTenantVariant(TestMinReadyLauncher):
    tenant_config_file = "config/launcher-min-ready/tenant-variant.yaml"

    def test_min_ready(self):
        for _ in iterate_timeout(60, "nodes to be ready"):
            nodes = self.launcher.api.nodes_cache.getItems()
            if len(nodes) != 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        self.waitUntilSettled()
        nodes = self.launcher.api.nodes_cache.getItems()
        self.assertEqual(5, len(nodes))

        nodes_by_label = self._nodes_by_label()
        self.assertEqual(4, len(nodes_by_label['debian-normal']))
        debian_normal_cfg_hashes = {
            n.label_config_hash for n in nodes_by_label['debian-normal']
        }
        self.assertEqual(2, len(debian_normal_cfg_hashes))

        files = {
            'zuul-extra.d/image.yaml': textwrap.dedent(
                '''
                - image:
                    name: debian
                    type: cloud
                    description: "Debian test image"
                '''
            )
        }
        self.addCommitToRepo('org/project1', 'Change label config', files)
        self.scheds.execute(lambda app: app.sched.reconfigure(app.config))
        self.waitUntilSettled()

        for _ in iterate_timeout(60, "nodes to be ready"):
            nodes = self.launcher.api.nodes_cache.getItems()
            if len(nodes) != 5:
                continue
            if all(n.state == n.State.READY for n in nodes):
                break

        nodes = self.launcher.api.nodes_cache.getItems()
        self.assertEqual(5, len(nodes))

        nodes_by_label = self._nodes_by_label()
        self.assertEqual(1, len(nodes_by_label['debian-emea']))
        self.assertEqual(4, len(nodes_by_label['debian-normal']))
        debian_normal_cfg_hashes = {
            n.label_config_hash for n in nodes_by_label['debian-normal']
        }
        self.assertEqual(2, len(debian_normal_cfg_hashes))


class TestLauncherImagePermissions(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    tenant_config_file = 'config/launcher-config-error/main.yaml'
    mock_aws = mock_aws()

    @skip("TODO: re-enable this check")
    def test_image_permissions(self):
        # The check to implement this was too costly (or flawed) in
        # production so was emergency disabled.  It is not strictly
        # necessary since we perform a permissions check when we
        # freeze the job (and that code path also has a test which is
        # still enabled); this check is to find the error sooner for
        # the user.
        # TODO: attempt to re-implement if possible.
        self.waitUntilSettled()
        self.assertHistory([])

        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")
        errors = tenant.layout.loading_errors
        self.assertEqual(len(errors), 1)
        self.assertIn('The image build job', errors[0].error)
