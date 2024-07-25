# Copyright 2021-2024 Acme Gating, LLC
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

from zuul.zk.zkobject import ZKObjectMember


class StateMachine:

    def __init__(self, state):
        self.state = state
        self.complete = False

    @property
    def step(self):
        return self.state.step

    @step.setter
    def step(self, step):
        self.state.step = step

    def advance(self):
        pass


class CreateState(ZKObjectMember):
    START = 'start'

    def __init__(self, node):
        super().__init__(node)
        self._set(
            step=self.START,
            start_time=time.monotonic(),
            external_id=None,
            image_external_id=None,
        )

    def serialize(self):
        return dict(
            image_external_id=self.image_external_id,
            step=self.step,
            start_time=self.start_time,
            external_id=self.external_id,
        )


class DeleteState(ZKObjectMember):
    START = 'start'

    def __init__(self, node):
        super().__init__(node)
        self._set(
            step=self.START,
            external_id=None
        )

    def serialize(self):
        return dict(
            step=self.state,
            external_id=self.external_id,
        )


class Instance:
    """Represents a cloud instance

    This class is used by the State Machine Driver classes to
    represent a standardized version of a remote cloud instance.
    Implement this class in your driver, override the :py:meth:`load`
    method, and supply as many of the fields as possible.

    The following attributes are required:

    * ready: bool (whether the instance is ready)
    * deleted: bool (whether the instance is in a deleted state)
    * external_id: str or dict (the unique id of the instance)
    * interface_ip: str
    * metadata: dict

    The following are optional:

    * public_ipv4: str
    * public_ipv6: str
    * private_ipv4: str
    * cloud: str
    * az: str
    * region: str
    * host_id: str
    * driver_data: any
    * slot: int

    And the following are even more optional (as they are usually
    already set from the image configuration):

    * username: str
    * python_path: str
    * shell_type: str
    * connection_port: str
    * connection_type: str
    * host_keys: [str]

    This is extremely optional, in fact, it's difficult to imagine
    that it's useful for anything other than the metastatic driver:

    * node_attributes: dict

    """
    def __init__(self):
        self.ready = False
        self.deleted = False
        self.external_id = None
        self.public_ipv4 = None
        self.public_ipv6 = None
        self.private_ipv4 = None
        self.interface_ip = None
        self.cloud = None
        self.az = None
        self.region = None
        self.host_id = None
        self.metadata = {}
        self.driver_data = None
        self.slot = None

    def __repr__(self):
        state = []
        if self.ready:
            state.append('ready')
        if self.deleted:
            state.append('deleted')
        state = ' '.join(state)
        return '<{klass} {external_id} {state}>'.format(
            klass=self.__class__.__name__,
            external_id=self.external_id,
            state=state)

    def getQuotaInformation(self):
        """Return quota information about this instance.

        :returns: A :py:class:`QuotaInformation` object.
        """
        raise NotImplementedError()


class Resource:
    """Represents a cloud resource

    This could be an instance, a disk, a floating IP, or anything
    else.  It is used by the driver to detect leaked resources so the
    adapter can clean them up.

    The `type` attribute should be an alphanumeric string suitable for
    inclusion in a statsd metric name.

    The `metadata` attribute is a dictionary of key/value pairs
    initially supplied by the driver to the adapter when an instance
    or image was created.  This is used by the driver to detect leaked
    resources.  The adapter may add any other information to this
    instance for its own bookeeping (resource type, id, etc).

    The 'plural_metric_name' attribute is set in the constructor
    automatically; override this value if necessary.

    :param str type: The type of resource.
    :param dict metadata: A dictionary of metadata for the resource.

    """

    def __init__(self, metadata, type):
        self.type = type
        self.plural_metric_name = type + 's'
        self.metadata = metadata
