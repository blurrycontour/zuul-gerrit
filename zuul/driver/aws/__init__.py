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

from zuul.driver import Driver, ConnectionInterface, ProviderInterface
from zuul.driver.aws import awsconnection, awsprovider


class AwsDriver(Driver, ConnectionInterface, ProviderInterface):
    name = 'aws'

    def getConnection(self, name, config):
        return awsconnection.AwsConnection(self, name, config)

    def getProvider(self, connection, provider_config):
        return awsprovider.AwsProvider(self, connection, provider_config)

    def getProviderSchema(self):
        return awsprovider.AwsProviderSchema().getProviderSchema()
