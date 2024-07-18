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

import voluptuous as vs

from zuul.driver.aws.awsendpoint import (
    AwsCreateStateMachine,
    AwsDeleteStateMachine,
)
from zuul.driver.aws.const import (
    SPOT,
    ON_DEMAND,
    VOLUME_QUOTA_CODES,
)
from zuul.driver.util import QuotaInformation
from zuul.provider import (
    BaseProvider,
    BaseProviderFlavor,
    BaseProviderImage,
    BaseProviderLabel,
    BaseProviderSchema,
)


class AwsProviderImage(BaseProviderImage):
    pass


class AwsProviderFlavor(BaseProviderFlavor):
    def __init__(self, config):
        super().__init__(config)
        self.instance_type = config['instance-type']
        self.volume_type = config.get('volume-type')
        self.dedicated_host = config.get('dedicated-host', False)


class AwsProviderLabel(BaseProviderLabel):
    def __init__(self, config):
        super().__init__(config)


class AwsProvider(BaseProvider, subclass_id='aws'):
    log = logging.getLogger("zuul.AwsProvider")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # In listResources, we reconcile AMIs which appear to be
        # imports but have no nodepool tags, however it's possible
        # that these aren't nodepool images.  If we determine that's
        # the case, we'll add their ids here so we don't waste our
        # time on that again.
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

    def parseConfig(self, config):
        data = super().parseConfig(config)
        data['region'] = config['region']
        data['object_storage'] = config.get('object-storage')
        return data

    def parseImage(self, image_config):
        return AwsProviderImage(image_config)

    def parseFlavor(self, flavor_config):
        return AwsProviderFlavor(flavor_config)

    def parseLabel(self, label_config):
        return AwsProviderLabel(label_config)

    def getEndpoint(self):
        return self.driver.getEndpoint(self)

    def getCreateStateMachine(self, hostname, label, image_external_id,
                              metadata, request, az, log):
        return AwsCreateStateMachine(self.endpoint, hostname, label,
                                     image_external_id, metadata,
                                     request, log)

    def getDeleteStateMachine(self, external_id, log):
        return AwsDeleteStateMachine(self.endpoint, external_id, log)

    def listInstances(self):
        return self.endpoint.listInstances()

    def listResources(self):
        bucket_name = self.object_storage.get('bucket-name')

        self.endpoint._tagSnapshots(
            self.tenant_scoped_name, self.not_our_snapshots)
        self.endpoint._tagAmis(
            self.tenant_scoped_name, self.not_our_images)
        return self.endpoint.listResources(bucket_name)

    def deleteResource(self, resource):
        bucket_name = self.object_storage.get('bucket-name')
        self.endpoint.deleteResource(resource, bucket_name)

    def getQuotaLimits(self):
        # Get the instance and volume types that this provider handles
        instance_types = {}
        host_types = set()
        volume_types = set()
        ec2_quotas = self.endpoint._listEC2Quotas()
        ebs_quotas = self.endpoint._listEBSQuotas()
        for label in self.labels.values():
            if label.dedicated_host:
                host_types.add(label.instance_type)
            else:
                if label.instance_type not in instance_types:
                    instance_types[label.instance_type] = set()
                instance_types[label.instance_type].add(
                    SPOT if label.use_spot else ON_DEMAND)
            if label.volume_type:
                volume_types.add(label.volume_type)
        args = dict(default=math.inf)
        for instance_type in instance_types:
            for market_type_option in instance_types[instance_type]:
                code = self.endpoint._getQuotaCodeForInstanceType(
                    instance_type, market_type_option)
                if code in args:
                    continue
                if not code:
                    continue
                if code not in ec2_quotas:
                    self.log.warning(
                        "AWS quota code %s for instance type: %s not known",
                        code, instance_type)
                    continue
                args[code] = ec2_quotas[code]
        for host_type in host_types:
            code = self.endpoint._getQuotaCodeForHostType(host_type)
            if code in args:
                continue
            if not code:
                continue
            if code not in ec2_quotas:
                self.log.warning(
                    "AWS quota code %s for host type: %s not known",
                    code, host_type)
                continue
            args[code] = ec2_quotas[code]
        for volume_type in volume_types:
            vquota_codes = VOLUME_QUOTA_CODES.get(volume_type)
            if not vquota_codes:
                self.log.warning(
                    "Unknown quota code for volume type: %s",
                    volume_type)
                continue
            for resource, code in vquota_codes.items():
                if code in args:
                    continue
                if code not in ebs_quotas:
                    self.log.warning(
                        "AWS quota code %s for volume type: %s not known",
                        code, volume_type)
                    continue
                value = ebs_quotas[code]
                # Unit mismatch: storage limit is in TB, but usage
                # is in GB.  Translate the limit to GB.
                if resource == 'storage':
                    value *= 1000
                args[code] = value
        return QuotaInformation(**args)

    def getQuotaForLabel(self, label):
        return self.endpoint.getQuotaForLabel(label)

    def uploadImage(self, provider_image, image_name,
                    filename, image_format, metadata, md5, sha256):
        bucket_name = self.object_storage.get('bucket-name')
        timeout = self.image_import_timeout
        return self.endpoint.uploadImage(
            provider_image, image_name,
            filename, image_format, metadata, md5, sha256,
            bucket_name, timeout)

    def deleteImage(self, external_id):
        self.endpoint.deleteImage(external_id)


class AwsProviderSchema(BaseProviderSchema):
    def getImageSchema(self):
        base_schema = super().getImageSchema()

        # This is AWS syntax, so we allow upper or lower case
        image_filters = {
            vs.Any('Name', 'name'): str,
            vs.Any('Values', 'values'): [str]
        }
        cloud_schema = base_schema.extend({
            'image-id': str,
            'image-filters': [image_filters],
        })

        def validator(data):
            if data.get('type') == 'cloud':
                return cloud_schema(data)
            return base_schema(data)

        return validator

    def getFlavorSchema(self):
        base_schema = super().getLabelSchema()

        schema = base_schema.extend({
            vs.Required('instance-type'): str,
            'volume-type': str,
            'dedicated-host': bool,
        })

        return schema

    def getLabelSchema(self):
        base_schema = super().getLabelSchema()
        return base_schema

    def getProviderSchema(self):
        # TODO: validate tag values are strings
        schema = super().getProviderSchema()
        object_storage = {
            vs.Required('bucket-name'): str,
        }

        schema = schema.extend({
            vs.Required('region'): str,
            'object-storage': object_storage,
        })
        return schema
