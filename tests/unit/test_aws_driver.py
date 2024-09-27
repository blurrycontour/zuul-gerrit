# Copyright 2024 Acme Gating, LLC
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

import concurrent.futures
import contextlib
import time
from unittest import mock

import fixtures
from moto import mock_aws
import boto3

from zuul.driver.aws import AwsDriver
from zuul.driver.aws.awsmodel import AwsProviderNode
from zuul.launcher.server import Launcher

from tests.fake_aws import FakeAws, FakeAwsProviderEndpoint
from tests.base import (
    TestConnectionRegistry,
    ZuulTestCase,
    iterate_timeout,
    simple_layout,
)


class TestAwsDriver(ZuulTestCase):
    config_file = 'zuul-connections-nodepool.conf'
    mock_aws = mock_aws()

    def setUp(self):
        self.initTestConfig()
        aws_id = 'AK000000000000000000'
        aws_key = '0123456789abcdef0123456789abcdef0123456789abcdef'
        self.useFixture(
            fixtures.EnvironmentVariable('AWS_ACCESS_KEY_ID', aws_id))
        self.useFixture(
            fixtures.EnvironmentVariable('AWS_SECRET_ACCESS_KEY', aws_key))

        self.fake_aws = FakeAws()
        self.mock_aws.start()

        self.ec2 = boto3.resource('ec2', region_name='us-west-2')
        self.ec2_client = boto3.client('ec2', region_name='us-west-2')
        self.s3 = boto3.resource('s3', region_name='us-west-2')
        self.s3_client = boto3.client('s3', region_name='us-west-2')
        self.iam = boto3.resource('iam', region_name='us-west-2')
        self.s3.create_bucket(
            Bucket='zuul',
            CreateBucketConfiguration={'LocationConstraint': 'us-west-2'})

        # A list of args to method calls for validation
        self.run_instances_calls = []
        self.run_instances_exception = None
        self.allocate_hosts_exception = None
        self.register_image_calls = []

        # TEST-NET-3
        ipv6 = False
        if ipv6:
            # This is currently unused, but if moto gains IPv6 support
            # on instance creation, this may be useful.
            self.vpc = self.ec2_client.create_vpc(
                CidrBlock='203.0.113.0/24',
                AmazonProvidedIpv6CidrBlock=True)
            ipv6_cidr = self.vpc['Vpc'][
                'Ipv6CidrBlockAssociationSet'][0]['Ipv6CidrBlock']
            ipv6_cidr = ipv6_cidr.split('/')[0] + '/64'
            self.subnet = self.ec2_client.create_subnet(
                CidrBlock='203.0.113.128/25',
                Ipv6CidrBlock=ipv6_cidr,
                VpcId=self.vpc['Vpc']['VpcId'])
            self.subnet_id = self.subnet['Subnet']['SubnetId']
        else:
            self.vpc = self.ec2_client.create_vpc(CidrBlock='203.0.113.0/24')
            self.subnet = self.ec2_client.create_subnet(
                CidrBlock='203.0.113.128/25', VpcId=self.vpc['Vpc']['VpcId'])
            self.subnet_id = self.subnet['Subnet']['SubnetId']

        profile = self.iam.create_instance_profile(
            InstanceProfileName='not-a-real-profile')
        self.instance_profile_name = profile.name
        self.instance_profile_arn = profile.arn

        self.security_group = self.ec2_client.create_security_group(
            GroupName='zuul-nodes', VpcId=self.vpc['Vpc']['VpcId'],
            Description='Zuul Nodes')
        self.security_group_id = self.security_group['GroupId']

        self.patch(AwsDriver, '_endpoint_class', FakeAwsProviderEndpoint)
        self.patch(FakeAwsProviderEndpoint,
                   '_FakeAwsProviderEndpoint__testcase', self)

        default_ec2_quotas = {
            'L-1216C47A': 100,
            'L-43DA4232': 100,
            'L-34B43A08': 100,
        }
        default_ebs_quotas = {
            'L-D18FCD1D': 100.0,
            'L-7A658B76': 100.0,
        }
        ec2_quotas = self.test_config.driver.aws.get(
            'ec2_quotas', default_ec2_quotas)
        ebs_quotas = self.test_config.driver.aws.get(
            'ebs_quotas', default_ebs_quotas)
        self.patch(FakeAwsProviderEndpoint,
                   '_FakeAwsProviderEndpoint__ec2_quotas', ec2_quotas)
        self.patch(FakeAwsProviderEndpoint,
                   '_FakeAwsProviderEndpoint__ebs_quotas', ebs_quotas)

        super().setUp()

    def tearDown(self):
        self.mock_aws.stop()
        super().tearDown()

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_aws_config(self):
        aws_conn = self.scheds.first.sched.connections.connections['aws']
        self.assertEqual('fake', aws_conn.access_key_id)
        layout = self.scheds.first.sched.abide.tenants.get('tenant-one').layout
        provider = layout.providers['aws-us-east-1-main']
        endpoint = provider.getEndpoint()
        self.assertEqual([], list(endpoint.listInstances()))

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_aws_launcher(self):
        for _ in iterate_timeout(
                30, "scheduler and launcher to have the same layout"):
            if (self.scheds.first.sched.local_layout_state.get("tenant-one") ==
                self.launcher.local_layout_state.get("tenant-one")):
                break
        providers = self.launcher.tenant_providers['tenant-one']
        self.assertEqual(1, len(providers))
        provider = providers[0]
        self.assertNotEqual([], list(provider.listResources()))

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

            launcher_connections = TestConnectionRegistry(
                self.config, self.test_config,
                self.additional_event_queues,
                self.upstream_root, self.poller_events,
                self.git_url_with_auth, self.addCleanup)
            launcher_connections.configure(self.config, providers=True)
            self.launcher = Launcher(
                self.config,
                launcher_connections)
            self.launcher.start()

        self.waitUntilSettled()
        self.assertEqual(self.getJobFromHistory('check-job').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(self.getJobFromHistory('check-job').node,
                         'debian-normal')

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_state_machines_instance(self):
        self._test_state_machines("debian-normal")

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_state_machines_dedicated_host(self):
        self._test_state_machines("debian-dedicated")

    def _test_state_machines(self, label):
        # Stop the launcher main loop, so we can drive the state machine
        # on our own.
        self.launcher._running = False
        self.waitUntilSettled()

        layout = self.scheds.first.sched.abide.tenants.get('tenant-one').layout
        provider = layout.providers['aws-us-east-1-main']

        with self.createZKContext(None) as ctx:
            node = AwsProviderNode.new(ctx, label=label)
            execute_future = False
            for _ in iterate_timeout(60, "create state machine to complete"):
                with node.activeContext(ctx):
                    # Re-create the SM from the state in ZK
                    sm = provider.getCreateStateMachine(node, None, self.log)
                    node.create_state_machine = sm
                    with self._block_futures():
                        sm.advance()
                    # If there are pending futures we will try to re-create
                    # the SM once from the state and then advance it once
                    # more so the futures can complete.
                    pending_futures = [
                        f for f in (sm.host_create_future, sm.create_future)
                        if f]
                    if pending_futures:
                        if execute_future:
                            concurrent.futures.wait(pending_futures)
                            sm.advance()
                        # Toggle future execution flag
                        execute_future = not execute_future
                if sm.complete:
                    break

            for _ in iterate_timeout(60, "delete state machine to complete"):
                with node.activeContext(ctx):
                    # Re-create the SM from the state in ZK
                    sm = provider.getDeleteStateMachine(node, self.log)
                    node.delete_state_machine = sm
                    sm.advance()
                if sm.complete:
                    break
                # Avoid busy-looping as we have to wait for the TTL
                # cache to expire.
                time.sleep(0.5)

    @contextlib.contextmanager
    def _block_futures(self):
        with (mock.patch(
                'zuul.driver.aws.awsendpoint.AwsProviderEndpoint.'
                '_completeAllocateHost', return_value=None),
              mock.patch(
                'zuul.driver.aws.awsendpoint.AwsProviderEndpoint.'
                '_completeCreateInstance', return_value=None)):
            yield
