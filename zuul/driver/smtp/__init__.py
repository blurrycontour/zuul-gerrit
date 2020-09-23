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
from zuul import model
from zuul.driver.smtp.smtpreporter import SMTPReporter
from zuul.connection import BaseConnection
from zuul.driver import Driver, ConnectionInterface, ReporterInterface
from zuul.driver.smtp import smtpconnection
from zuul.driver.smtp import smtpreporter


class SMTPDriver(Driver, ConnectionInterface, ReporterInterface):
    name: str = 'smtp'

    def getConnection(self, name: str,
                      config: Dict[str, Any]) -> BaseConnection:
        return smtpconnection.SMTPConnection(self, name, config)

    def getReporter(self, connection: BaseConnection, pipeline: model.Pipeline,
                    config: Optional[Dict[str, Any]] = None) -> SMTPReporter:
        return SMTPReporter(self, connection, config)

    def getReporterSchema(self) -> voluptuous.Schema:
        return smtpreporter.getSchema()
