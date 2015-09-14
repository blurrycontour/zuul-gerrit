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


class SQLAlchemyConnection(BaseConnection):
    driver_name = 'sqlalchemy'
    log = logging.getLogger("connection.sqlalchemy")

    def __init__(self, connection_name, connection_config):

        super(SQLAlchemyConnection, self).__init__(connection_name,
                                                   connection_config)

        self.dburi = self.connection_config.get('dburi')
        self.engine = sqlalchemy.create_engine(self.dburi)


def getSchema():
    sqlalchemy_connection = v.Any(str, v.Schema({}, extra=True))
    return sqlalchemy_connection
