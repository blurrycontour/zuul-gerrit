# Copyright 2018 Red Hat, Inc.
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

from typing import Dict, Any, Optional, Type
import voluptuous
from zuul import model
from zuul.connection import BaseConnection
from zuul.driver import Driver, ConnectionInterface, TriggerInterface
from zuul.driver import SourceInterface, ReporterInterface
from zuul.driver.gitlab import gitlabconnection
from zuul.driver.gitlab import gitlabmodel
from zuul.driver.gitlab import gitlabsource
from zuul.driver.gitlab import gitlabreporter
from zuul.driver.gitlab import gitlabtrigger
from zuul.source import BaseSource
from zuul.driver.gitlab.gitlabreporter import GitlabReporter


class GitlabDriver(Driver, ConnectionInterface, TriggerInterface,
                   SourceInterface, ReporterInterface):
    name: str = 'gitlab'

    def getConnection(self, name: str,
                      config: Dict[str, Any]) -> BaseConnection:
        return gitlabconnection.GitlabConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return gitlabtrigger.GitlabTrigger(self, connection, config)

    def getTriggerEventClass(self) -> Type[gitlabmodel.GitlabTriggerEvent]:
        return gitlabmodel.GitlabTriggerEvent

    def getSource(self, connection: BaseConnection) -> BaseSource:
        return gitlabsource.GitlabSource(self, connection)

    def getReporter(self, connection: BaseConnection, pipeline: model.Pipeline,
                    config: Optional[Dict[str, Any]] = None) -> GitlabReporter:
        return GitlabReporter(self, connection, pipeline, config)

    def getTriggerSchema(self):
        return gitlabtrigger.getSchema()

    def getReporterSchema(self) -> voluptuous.Schema:
        return gitlabreporter.getSchema()

    def getRequireSchema(self):
        return gitlabsource.getRequireSchema()

    def getRejectSchema(self):
        return gitlabsource.getRejectSchema()
