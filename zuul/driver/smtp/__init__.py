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

from typing import Any, Dict, Optional

import voluptuous as vs

from zuul.connection import BaseConnection
from zuul.driver import ConnectionInterface, Driver, ReporterInterface
from zuul.driver.smtp import smtpconnection, smtpreporter
from zuul.model import Pipeline


class SMTPDriver(Driver, ConnectionInterface, ReporterInterface):
    name = 'smtp'

    def getConnection(
        self,
        name: str,
        config: Dict[str, Any],
    ) -> BaseConnection:
        return smtpconnection.SMTPConnection(self, name, config)

    def getReporter(
        self,
        connection: BaseConnection,
        pipeline: Pipeline,
        config: Optional[Dict[str, Any]] = None,
    ) -> smtpreporter.SMTPReporter:
        return smtpreporter.SMTPReporter(self, connection, config)

    def getReporterSchema(self) -> vs.Schema:
        return smtpreporter.getSchema()
