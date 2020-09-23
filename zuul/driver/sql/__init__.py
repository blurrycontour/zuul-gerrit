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

from typing import Dict, Any, Optional
import voluptuous
from zuul.driver.sql.sqlreporter import SQLReporter
from zuul import model
from zuul.connection import BaseConnection
from zuul.driver import Driver, ConnectionInterface, ReporterInterface
from zuul.driver.sql import sqlconnection
from zuul.driver.sql import sqlreporter
from zuul.lib import capabilities as cpb


class SQLDriver(Driver, ConnectionInterface, ReporterInterface):
    name: str = 'sql'

    def __init__(self):
        self.tenant_connections = {}
        cpb.capabilities_registry.register_capabilities(
            'job_history', True)

    def reconfigure(self, tenant):
        # NOTE(corvus): This stores the connection of the first
        # reporter seen for each tenant; we should figure out how to
        # support multiple connections for a tenant (how do we deal
        # with pagination of queries across multiple connections), or
        # otherwise, require there only be one connection in a tenant.
        if tenant.name in self.tenant_connections:
            del self.tenant_connections[tenant.name]
        for pipeline in tenant.layout.pipelines.values():
            reporters = (pipeline.start_actions + pipeline.success_actions
                         + pipeline.failure_actions
                         + pipeline.merge_failure_actions)
            for reporter in reporters:
                if not isinstance(reporter, SQLReporter):
                    continue
                self.tenant_connections[tenant.name] = reporter.connection
                return

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def getConnection(self, name: str,
                      config: Dict[str, Any]) -> BaseConnection:
        return sqlconnection.SQLConnection(self, name, config)

    def getReporter(self, connection: BaseConnection, pipeline: model.Pipeline,
                    config: Optional[Dict[str, Any]]=None) -> SQLReporter:
        return SQLReporter(self, connection, config)

    def getReporterSchema(self) -> voluptuous.Schema:
        return sqlreporter.getSchema()
