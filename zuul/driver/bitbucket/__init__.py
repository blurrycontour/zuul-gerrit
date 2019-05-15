# Copyright 2019 Smaato, Inc.
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

from zuul.driver import Driver, ConnectionInterface
from zuul.driver import SourceInterface, ReporterInterface
from zuul.driver import TriggerInterface
from zuul.driver.bitbucket import bitbucketconnection
from zuul.driver.bitbucket import bitbucketsource
from zuul.driver.bitbucket import bitbucketreporter


class BitbucketDriver(Driver, ConnectionInterface, SourceInterface,
                      ReporterInterface):
    name = 'bitbucket'

    def getConnection(self, name, config):
        return bitbucketconnection.BitbucketConnection(self, name, config)

    def getSource(self, connection):
        return bitbucketsource.BitbucketSource(self, connection)

    def getRequireSchema(self):
        return {}

    def getRejectSchema(self):
        return {}

    def getReporter(self, connection, pipeline, config=None):
        return bitbucketreporter.BitbucketReporter(
            self, connection, pipeline, config)

    def getReporterSchema(self):
        return bitbucketreporter.getSchema()

    def getTrigger(self, connection, config=None):
        # FIXME
        pass

    def getTriggerSchema(self):
        # FIXME
        pass
