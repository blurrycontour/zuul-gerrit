# Copyright 2017 Red Hat, Inc.
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
from zuul.driver import ConnectionInterface
from zuul.driver import Driver
from zuul.driver import ReporterInterface
from zuul.driver.fedmsg import fedmsgconnection
from zuul.driver.fedmsg import fedmsgreporter


class FedmsgDriver(Driver, ConnectionInterface, ReporterInterface):
    name = 'fedmsg'

    def getConnection(self, name, config):
        return fedmsgconnection.FedmsgConnection(self, name, config)

    def getReporter(self, connection, config=None):
        return fedmsgreporter.FedmsgReporter(self, connection, config)

    def getReporterSchema(self):
        return fedmsgreporter.getSchema()
