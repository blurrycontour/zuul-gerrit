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

from zuul.driver import Driver, ConnectionInterface, TriggerInterface
from zuul.driver import SourceInterface
from zuul.driver.bitbucketcloud import bitbucketcloudconnection
from zuul.driver.bitbucketcloud import bitbucketcloudsource
from zuul.driver.bitbucketcloud import bitbucketcloudtrigger
from zuul.driver.bitbucketcloud import bitbucketcloudreporter


class BitbucketCloudDriver(
        Driver,
        ConnectionInterface,
        SourceInterface,
        TriggerInterface):
    name = 'bitbucketcloud'

    def getConnection(self, name, config):
        return bitbucketcloudconnection.BitbucketCloudConnection(
            self, name, config)

    def getSource(self, connection):
        return bitbucketcloudsource.BitbucketCloudSource(self, connection)

    def getTrigger(self, connection, config=None):
        return bitbucketcloudtrigger.BitbucketCloudTrigger(
            self, connection, config)

    def getTriggerSchema(self):
        return bitbucketcloudtrigger.getSchema()

    def getRequireSchema(self):
        return {}

    def getRejectSchema(self):
        return {}

    def getReporterSchema(self):
        return bitbucketcloudreporter.getSchema()

    def getReporter(self, connection, pipeline, config=None):
        return bitbucketcloudreporter.BitbucketCloudReporter(
            self, connection, pipeline, config)
