# Copyright 2020 Motional.
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
from zuul.driver.bbserver import bbserverconnection
from zuul.driver.bbserver import bbserversource
from zuul.driver.bbserver import bbservertrigger


class BitbucketServerDriver(Driver, ConnectionInterface,
                            TriggerInterface, SourceInterface):
    name = 'bitbucketserver'

    def getConnection(self, name, config):
        return bbserverconnection.BitbucketServerConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return bbservertrigger.BitbucketServerTrigger(self, connection, config)

    def getSource(self, connection):
        return bbserversource.BitbucketServerSource(self, connection)

    def getTriggerSchema(self):
        return bbservertrigger.getSchema()

    def getRequireSchema(self):
        return bbserversource.getRequireSchema()

    def getRejectSchema(self):
        return bbserversource.getRejectSchema()
