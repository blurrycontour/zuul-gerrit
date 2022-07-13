# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2016 Red Hat, Inc.
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

from zuul.driver import (
    Driver, ConnectionInterface, ReporterInterface, SourceInterface,
    TriggerInterface
)
from zuul.driver.gitea import giteaconnection
from zuul.driver.gitea import giteamodel
from zuul.driver.gitea import giteareporter
from zuul.driver.gitea import giteasource
from zuul.driver.gitea import giteatrigger


class GiteaDriver(Driver, ConnectionInterface, SourceInterface,
                  TriggerInterface, ReporterInterface):
    name = "gitea"

    def getConnection(self, name, config):
        return giteaconnection.GiteaConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return giteatrigger.GiteaTrigger(self, connection, config)

    def getTriggerSchema(self):
        return giteatrigger.getSchema()

    def getTriggerEventClass(self):
        return giteamodel.GiteaTriggerEvent

    def getSource(self, connection):
        return giteasource.GiteaSource(self, connection)

    def getReporter(self, connection, pipeline, config=None):
        return giteareporter.GiteaReporter(
            self, connection, pipeline, config)

    def getReporterSchema(self):
        return giteareporter.getSchema()

    def getRequireSchema(self):
        return {}

    def getRejectSchema(self):
        return {}
