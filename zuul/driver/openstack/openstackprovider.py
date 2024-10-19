# Copyright 2022-2024 Acme Gating, LLC
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
import math

import zuul.provider.schema as provider_schema
from zuul.lib.voluputil import (
    Required, Optional, Nullable, discriminate, assemble, RequiredExclusive,
)

import voluptuous as vs

from zuul.driver.openstack.openstackendpoint import (
    OpenstackCreateStateMachine,
    OpenstackDeleteStateMachine,
)
from zuul.driver.util import QuotaInformation
from zuul.provider import (
    BaseProvider,
    BaseProviderFlavor,
    BaseProviderImage,
    BaseProviderLabel,
    BaseProviderSchema,
)


class OpenstackProviderImage(BaseProviderImage):
    openstack_image_filters = {
        'name': str,
        'values': [str],
    }
    openstack_cloud_schema = vs.Schema({
        vs.Exclusive(Required('image-id'), 'spec'): str,
        vs.Exclusive(Required('image-filters'), 'spec'): [
            openstack_image_filters],
        Optional('config-drive', default=True): bool,
        Required('type'): 'cloud',
    })
    cloud_schema = vs.All(
        assemble(
            BaseProviderImage.schema,
            openstack_cloud_schema,
        ),
        RequiredExclusive('image_id', 'image_filters',
                          msg=('Provide either '
                               '"image-filters", or "image-id" keys'))
    )
    inheritable_openstack_zuul_schema = vs.Schema({
        # None is an acceptable explicit value for imds-support
        Optional('config-drive', default=True): bool,
    })
    openstack_zuul_schema = vs.Schema({
        Required('type'): 'zuul',
        Optional('tags', default=dict): {str: str},
    })
    zuul_schema = assemble(
        BaseProviderImage.schema,
        openstack_zuul_schema,
        inheritable_openstack_zuul_schema,
    )

    inheritable_schema = assemble(
        BaseProviderImage.inheritable_schema,
        inheritable_openstack_zuul_schema,
    )
    schema = vs.Union(
        cloud_schema, zuul_schema,
        discriminant=discriminate(
            lambda val, alt: val['type'] == alt['type']))

    def __init__(self, image_config, provider_config, image_format):
        self.image_id = None
        self.image_filters = None
        super().__init__(image_config, provider_config)
        self.format = image_format
        # Implement provider defaults
        if self.connection_type is None:
            self.connection_type = 'ssh'
        if self.connection_port is None:
            self.connection_port = 22


class OpenstackProviderFlavor(BaseProviderFlavor):
    openstack_flavor_schema = vs.Schema({
        Required('flavor-name'): str,
    })

    inheritable_schema = assemble(
        BaseProviderFlavor.inheritable_schema,
        provider_schema.cloud_flavor,
    )
    schema = assemble(
        BaseProviderFlavor.schema,
        provider_schema.cloud_flavor,
        openstack_flavor_schema,
    )


class OpenstackProviderLabel(BaseProviderLabel):
    openstack_label_schema = vs.Schema({
        Optional('volume-size'): Nullable(int),
        Optional('userdata'): Nullable(str),
    })
    inheritable_openstack_label_schema = vs.Schema({
        Optional('auto-floating-ip', default=True): bool,
        Optional('boot-from-volume', default=False): bool,
        Optional('networks', default=[]): [str],  # TODO: as_list?
        Optional('security-groups', default=[]): [str],  # TODO: as_list?
    })
    inheritable_schema = assemble(
        BaseProviderLabel.inheritable_schema,
        provider_schema.ssh_label,
        inheritable_openstack_label_schema,
    )
    schema = assemble(
        BaseProviderLabel.schema,
        provider_schema.ssh_label,
        inheritable_openstack_label_schema,
        openstack_label_schema,
    )


class OpenstackProviderSchema(BaseProviderSchema):
    def getLabelSchema(self):
        return OpenstackProviderLabel.schema

    def getImageSchema(self):
        return OpenstackProviderImage.schema

    def getFlavorSchema(self):
        return OpenstackProviderFlavor.schema

    def getProviderSchema(self):
        schema = super().getProviderSchema()

        openstack_provider_schema = vs.Schema({
            Optional('region'): Nullable(str),
        })
        return assemble(
            schema,
            openstack_provider_schema,
            OpenstackProviderImage.inheritable_schema,
            OpenstackProviderFlavor.inheritable_schema,
            OpenstackProviderLabel.inheritable_schema,
        )


class OpenstackProvider(BaseProvider, subclass_id='openstack'):
    log = logging.getLogger("zuul.OpenstackProvider")
    schema = OpenstackProviderSchema().getProviderSchema()

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # In listResources, we reconcile AMIs which appear to be
        # imports but have no nodepool tags, however it's possible
        # that these aren't nodepool images.  If we determine that's
        # the case, we'll add their ids here so we don't waste our
        # time on that again.  We do not need to serialize these;
        # these are ephemeral caches.
        self._set(
            not_our_images=set(),
            not_our_snapshots=set(),
        )

    @property
    def endpoint(self):
        ep = getattr(self, '_endpoint', None)
        if ep:
            return ep
        self._set(_endpoint=self.getEndpoint())
        return self._endpoint

    def parseImage(self, image_config, provider_config, connection):
        # We are not fully constructed yet at this point, so we need
        # to peek to get the region and endpoint.
        region = provider_config.get('region')
        endpoint = connection.driver._getEndpoint(connection, region)
        return OpenstackProviderImage(
            image_config, provider_config,
            image_format=endpoint.getImageFormat())

    def parseFlavor(self, flavor_config, provider_config, connection):
        return OpenstackProviderFlavor(flavor_config, provider_config)

    def parseLabel(self, label_config, provider_config, connection):
        return OpenstackProviderLabel(label_config, provider_config)

    def getEndpoint(self):
        return self.driver.getEndpoint(self)

    def getCreateStateMachine(self, node, image_external_id, log):
        # TODO: decide on a method of producing a hostname
        # that is max 15 chars.
        hostname = f"np{node.uuid[:13]}"
        label = self.labels[node.label]
        flavor = self.flavors[label.flavor]
        image = self.images[label.image]
        return OpenstackCreateStateMachine(
            self.endpoint,
            node,
            hostname,
            label,
            flavor,
            image,
            image_external_id,
            node.tags,
            log)

    def getDeleteStateMachine(self, node, log):
        return OpenstackDeleteStateMachine(self.endpoint, node, log)

    def listInstances(self):
        return self.endpoint.listInstances()

    def listResources(self):
        # TODO: implement
        return []

    def deleteResource(self, resource):
        # TODO: implement
        pass

    def getQuotaLimits(self):
        # TODO: implement
        args = dict(default=math.inf)
        return QuotaInformation(**args)

    def getQuotaForLabel(self, label):
        flavor = self.flavors[label.flavor]
        return self.endpoint.getQuotaForLabel(label, flavor)

    def uploadImage(self, provider_image, image_name,
                    filename, image_format, metadata, md5, sha256):
        # TODO make this configurable
        # timeout = self.image_import_timeout
        timeout = 300
        return self.endpoint.uploadImage(
            provider_image, image_name,
            filename, image_format, metadata, md5, sha256,
            timeout)

    def deleteImage(self, external_id):
        self.endpoint.deleteImage(external_id)
