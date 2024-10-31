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
import zuul.driver.aws.awsendpoint

from tests.fake_aws import FakeAws, FakeAwsProviderEndpoint
from tests.base import (
    iterate_timeout,
    simple_layout,
    return_data,
)
from tests.unit.test_launcher import ImageMocksFixture
from tests.unit.test_cloud_driver import BaseCloudDriverTest


class TestAwsDriver(BaseCloudDriverTest):
    config_file = 'zuul-connections-nodepool.conf'
    cloud_test_image_format = 'raw'
    cloud_test_provider_name = 'aws-us-east-1-main'
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
                        'sha256': ('59984dd82f51edb3777b969739a92780'
                                   'a520bb314b8d64b294d5de976bd8efb9'),
                        'md5sum': '262278e1632567a907e4604e9edd2e83',
                    }
                },
            ]
        }
    }

    def setUp(self):
        self.initTestConfig()
        aws_id = 'AK000000000000000000'
        aws_key = '0123456789abcdef0123456789abcdef0123456789abcdef'
        self.useFixture(
            fixtures.EnvironmentVariable('AWS_ACCESS_KEY_ID', aws_id))
        self.useFixture(
            fixtures.EnvironmentVariable('AWS_SECRET_ACCESS_KEY', aws_key))
        self.patch(zuul.driver.aws.awsendpoint, 'CACHE_TTL', 1)

        # Moto doesn't handle some aspects of instance creation, so we
        # intercept and log the calls.
        def _fake_run_instances(*args, **kwargs):
            self.__testcase.run_instances_calls.append(kwargs)
            if self.__testcase.run_instances_exception:
                raise self.__testcase.run_instances_exception
            return self.ec2_client.run_instances_orig(*args, **kwargs)

        self.fake_aws = FakeAws()
        self.mock_aws.start()
        # Must start responses after mock_aws
        self.useFixture(ImageMocksFixture())

        self.ec2 = boto3.resource('ec2', region_name='us-east-1')
        self.ec2_client = boto3.client('ec2', region_name='us-east-1')
        self.s3 = boto3.resource('s3', region_name='us-east-1')
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        self.iam = boto3.resource('iam', region_name='us-east-1')
        self.s3.create_bucket(Bucket='zuul')

        self.ec2_client.run_instances_orig = self.ec2_client.run_instances
        self.ec2_client.run_instances = _fake_run_instances

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

    def _assertProviderNodeAttributes(self, pnode):
        super()._assertProviderNodeAttributes(pnode)
        self.assertEqual(
            self.run_instances_calls[0]['BlockDeviceMappings'][0]['Ebs']
            ['Iops'], 1000)
        self.assertEqual(
            self.run_instances_calls[0]['BlockDeviceMappings'][0]['Ebs']
            ['Throughput'], 200)

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_aws_node_lifecycle(self):
        self._test_node_lifecycle('debian-normal')

    @simple_layout('layouts/aws/nodepool-image-snapshot.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    def test_aws_diskimage_snapshot(self):
        self._test_diskimage()

    @simple_layout('layouts/aws/nodepool-image-image.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    def test_aws_diskimage_image(self):
        self._test_diskimage()

    @simple_layout('layouts/aws/nodepool-image-ebs-direct.yaml',
                   enable_nodepool=True)
    @return_data(
        'build-debian-local-image',
        'refs/heads/master',
        debian_return_data,
    )
    def test_aws_diskimage_ebs_direct(self):
        self._test_diskimage()

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_state_machines_instance(self):
        self._test_state_machines("debian-normal")

    @simple_layout('layouts/nodepool.yaml', enable_nodepool=True)
    def test_state_machines_dedicated_host(self):
        self._test_state_machines("debian-dedicated")

    def _test_state_machines(self, label):
        # Stop the launcher main loop, so we can drive the state machine
        # on our own.
        self.waitUntilSettled()
        self.launcher._running = False
        self.launcher.wake_event.set()
        self.launcher.launcher_thread.join()

        layout = self.scheds.first.sched.abide.tenants.get('tenant-one').layout
        provider = layout.providers['aws-us-east-1-main']
        # Start the endpoint since we're going to use the scheduler's endpoint.
        provider.getEndpoint().start()

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
