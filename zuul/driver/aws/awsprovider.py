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

import boto3
import voluptuous as vs

from zuul.provider import (
    BaseProvider,
    BaseProviderSchema,
    BaseProviderLabel,
    BaseProviderEndpoint,
)


class AwsProviderLabel(BaseProviderLabel):
    pass


class AwsProviderEndpoint(BaseProviderEndpoint):
    """An AWS Endpoint corresponds to a single AWS region, and can include
    multiple availability zones."""

    def __init__(self, driver, connection, region):
        super().__init__(driver, connection)
        self.region = region

        self.aws = boto3.Session(
            aws_access_key_id=self.connection.access_key_id,
            aws_secret_access_key=self.connection.secret_access_key,
            profile_name=self.connection.profile,
            region_name=region,
        )
        self.ec2_client = self.aws.client("ec2")
        self.s3 = self.aws.resource('s3')
        self.s3_client = self.aws.client('s3')
        self.aws_quotas = self.aws.client("service-quotas")

    def testListAmis(self):
        # Just a demo method for testing
        paginator = self.ec2_client.get_paginator('describe_images')
        images = []
        for page in paginator.paginate():
            images.extend(page['Images'])
        return images


class AwsProvider(BaseProvider, subclass_id='aws'):
    log = logging.getLogger("zuul.AwsProvider")

    def parseConfig(self, config):
        data = super().parseConfig(config)
        data['region'] = config['region']
        return data

    def parseLabel(self, label_config):
        return AwsProviderLabel(label_config)

    def getEndpoint(self):
        return self.driver.getEndpoint(self)


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
