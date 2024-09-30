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

import urllib

from zuul.driver import Driver, ConnectionInterface, ProviderInterface
from zuul.driver.openstack import (
    openstackconnection,
    openstackmodel,
    openstackprovider,
    openstackendpoint,
)


class OpenstackDriver(Driver, ConnectionInterface, ProviderInterface):
    name = 'openstack'
    _endpoint_class = openstackendpoint.OpenstackProviderEndpoint

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.endpoints = {}

    def getConnection(self, name, config):
        return openstackconnection.OpenstackConnection(self, name, config)

    def getProvider(self, connection, tenant_name, canonical_name,
                    provider_config):
        return openstackprovider.OpenstackProvider(
            self, connection, tenant_name, canonical_name, provider_config)

    def getProviderClass(self):
        return openstackprovider.OpenstackProvider

    def getProviderSchema(self):
        return openstackprovider.OpenstackProviderSchema().getProviderSchema()

    def getProviderNodeClass(self):
        return openstackmodel.OpenstackProviderNode

    def getEndpoint(self, provider):
        region = provider.region or ''
        endpoint_id = '/'.join([
            urllib.parse.quote_plus(provider.connection.connection_name),
            urllib.parse.quote_plus(region),
        ])
        try:
            return self.endpoints[endpoint_id]
        except KeyError:
            pass
        endpoint = self._endpoint_class(
            self, provider.connection, provider.region)
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    def stop(self):
        for endpoint in self.endpoints.values():
            endpoint.stop()
