# Copyright 2014 Rackspace Australia
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

import logging
import sqlalchemy
import voluptuous as v

from zuul.connection import BaseConnection


class SQLConnection(BaseConnection):
    driver_name = 'sql'
    log = logging.getLogger("connection.sql")

    def __init__(self, connection_name, connection_config):

        super(SQLConnection, self).__init__(connection_name, connection_config)

        self.dburi = None
        self.engine = None
        self.connection = None
        try:
            self.dburi = self.connection_config.get('dburi')
            self.engine = sqlalchemy.create_engine(self.dburi)
        except sqlalchemy.exc.NoSuchModuleError:
            self.log.exception(
                "The required module for the dburi dialect isn't available. "
                "SQL connection %s will be unavailable." % connection_name)

    def connect(self):
        if not self.connection:
            self.connection = self.engine.connect()
        return self.connection

    def onStop(self):
        if self.connection:
            self.connection.close()


def getSchema():
    sql_connection = v.Any(str, v.Schema({}, extra=True))
    return sql_connection
