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
from zuul.driver.gerrit import (
    gerritconnection, gerritmodel, gerritreporter, gerritsource, gerrittrigger
)
from zuul.driver.util import to_list
from zuul.model import Pipeline
from zuul.source import BaseSource


class GerritDriver(Driver, ConnectionInterface, TriggerInterface,
                   SourceInterface, ReporterInterface):
    name = 'gerrit'

    def reconfigure(self, tenant):
        connection_checker_map = {}
        for pipeline in tenant.layout.pipelines.values():
            for trigger in pipeline.triggers:
                if isinstance(trigger, gerrittrigger.GerritTrigger):
                    con = trigger.connection
                    checkers = connection_checker_map.setdefault(con, [])
                    for trigger_item in to_list(trigger.config):
                        if trigger_item['event'] == 'pending-check':
                            d = {}
                            if 'uuid' in trigger_item:
                                d['uuid'] = trigger_item['uuid']
                            elif 'scheme' in trigger_item:
                                d['scheme'] = trigger_item['scheme']
                            checkers.append(d)
        for (con, checkers) in connection_checker_map.items():
            con.setWatchedCheckers(checkers)

    def getConnection(
        self,
        name: str,
        config: Dict[str, Any],
    ) -> BaseConnection:
        return gerritconnection.GerritConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return gerrittrigger.GerritTrigger(self, connection, config)

    def getTriggerEventClass(self) -> Type[gerritmodel.GerritTriggerEvent]:
        return gerritmodel.GerritTriggerEvent

    def getSource(self, connection: BaseConnection) -> BaseSource:
        return gerritsource.GerritSource(self, connection)

    def getReporter(
        self,
        connection: BaseConnection,
        pipeline: Pipeline,
        config: Optional[Dict[str, Any]] = None,
    ) -> gerritreporter.GerritReporter:
        return gerritreporter.GerritReporter(self, connection, config)

    def getTriggerSchema(self):
        return gerrittrigger.getSchema()

    def getReporterSchema(self) -> vs.Schema:
        return gerritreporter.getSchema()

    def getRequireSchema(self):
        return gerritsource.getRequireSchema()

    def getRejectSchema(self):
        return gerritsource.getRejectSchema()
