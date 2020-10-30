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

from typing import Any, Dict, Optional, Type

import voluptuous as vs

from zuul.connection import BaseConnection
from zuul.driver import (
    ConnectionInterface,
    Driver,
    ReporterInterface,
    SourceInterface,
    TriggerInterface,
)
from zuul.driver.gitlab import (
    gitlabconnection, gitlabmodel, gitlabreporter, gitlabsource, gitlabtrigger
)
from zuul.model import Pipeline
from zuul.source import BaseSource


class GitlabDriver(Driver, ConnectionInterface, TriggerInterface,
                   SourceInterface, ReporterInterface):
    name = 'gitlab'

    def getConnection(
        self,
        name: str,
        config: Dict[str, Any],
    ) -> BaseConnection:
        return gitlabconnection.GitlabConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return gitlabtrigger.GitlabTrigger(self, connection, config)

    def getTriggerEventClass(self) -> Type[gitlabmodel.GitlabTriggerEvent]:
        return gitlabmodel.GitlabTriggerEvent

    def getSource(self, connection: BaseConnection) -> BaseSource:
        return gitlabsource.GitlabSource(self, connection)

    def getReporter(
        self,
        connection: BaseConnection,
        pipeline: Pipeline,
        config: Optional[Dict[str, Any]] = None,
    ) -> gitlabreporter.GitlabReporter:
        return gitlabreporter.GitlabReporter(
            self, connection, pipeline, config
        )

    def getTriggerSchema(self):
        return gitlabtrigger.getSchema()

    def getReporterSchema(self) -> vs.Schema:
        return gitlabreporter.getSchema()

    def getRequireSchema(self):
        return gitlabsource.getRequireSchema()

    def getRejectSchema(self):
        return gitlabsource.getRejectSchema()
