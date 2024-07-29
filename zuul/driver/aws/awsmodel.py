# Copyright 2024 BMW Group
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

import uuid

from zuul import model
from zuul.provider import statemachine
from zuul.driver.aws.util import tag_list_to_dict


class AwsDeleteState(statemachine.DeleteState):
    HOST_RELEASING_START = 'start releasing host'
    HOST_RELEASING = 'releasing host'
    INSTANCE_DELETING_START = 'start deleting instance'
    INSTANCE_DELETING = 'deleting instance'
    COMPLETE = 'complete'


class AwsCreateState(statemachine.CreateState):
    HOST_ALLOCATING_SUBMIT = 'submit allocating host'
    HOST_ALLOCATING = 'allocating host'
    INSTANCE_CREATING_SUBMIT = 'submit creating instance'
    INSTANCE_CREATING = 'creating instance'
    COMPLETE = 'complete'

    def __init__(self, node):
        super().__init__(node)
        self._set(
            external_id=dict(),
            public_ipv4=None,
            public_ipv6=None,
            nic=None,
            instance=None,
            dedicated_host_id=None,
            attempts=0,
        )

    def getClientToken(self, op_id):
        node_uuid = uuid.UUID(self._zkparent.uuid)
        return uuid.uuid5(node_uuid, f"{self.attempts}-{op_id}").hex


class AwsProviderNode(model.ProviderNode, subclass_id="aws"):
    _create_state_class = AwsCreateState
    _delete_state_class = AwsDeleteState

    @property
    def hostname(self):
        # TODO: decide on a method of producing a hostname
        # that is max 15 chars.
        return f"np{self.uuid[:13]}"


class AwsInstance(statemachine.Instance):
    def __init__(self, region, instance, host, quota):
        super().__init__()
        self.external_id = dict()
        if instance:
            self.external_id['instance'] = instance['InstanceId']
        if host:
            self.external_id['host'] = host['HostId']
        self.metadata = tag_list_to_dict(instance.get('Tags'))
        self.private_ipv4 = instance.get('PrivateIpAddress')
        self.private_ipv6 = None
        self.public_ipv4 = instance.get('PublicIpAddress')
        self.public_ipv6 = None
        self.cloud = 'AWS'
        self.region = region
        self.az = None
        self.quota = quota

        self.az = instance.get('Placement', {}).get('AvailabilityZone')

        for iface in instance.get('NetworkInterfaces', [])[:1]:
            if iface.get('Ipv6Addresses'):
                v6addr = iface['Ipv6Addresses'][0]
                self.public_ipv6 = v6addr.get('Ipv6Address')
        self.interface_ip = (self.public_ipv4 or self.public_ipv6 or
                             self.private_ipv4 or self.private_ipv6)

    def getQuotaInformation(self):
        return self.quota


class AwsResource(statemachine.Resource):
    TYPE_HOST = 'host'
    TYPE_INSTANCE = 'instance'
    TYPE_AMI = 'ami'
    TYPE_SNAPSHOT = 'snapshot'
    TYPE_VOLUME = 'volume'
    TYPE_OBJECT = 'object'

    def __init__(self, metadata, type, id):
        super().__init__(metadata, type)
        self.id = id
