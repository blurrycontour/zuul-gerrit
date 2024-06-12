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

import logging

import voluptuous as vs

from zuul.provider import (
    BaseProvider,
    BaseProviderSchema,
    BaseProviderLabel,
)


class AwsProviderLabel(BaseProviderLabel):
    pass


class AwsProvider(BaseProvider):
    log = logging.getLogger("zuul.AwsProvider")

    def __init__(self, driver, connection, config):
        super().__init__(driver, connection, config)

    def parseLabel(self, label_config):
        return AwsProviderLabel(label_config)


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

    def getProviderSchema(self):
        schema = super().getProviderSchema()

        schema = schema.extend({
            vs.Required('region'): str,
        })
        return schema
