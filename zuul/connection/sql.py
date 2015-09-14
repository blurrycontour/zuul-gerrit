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

import alembic
import alembic.config
import sqlalchemy
import voluptuous as v

from zuul.connection import BaseConnection

BUILD_TABLE = 'zuul_build'
BUILD_METADATA_TABLE = BUILD_TABLE + '_metadata'


class SQLConnection(BaseConnection):
    driver_name = 'sql'
    log = logging.getLogger("connection.sql")

    def __init__(self, connection_name, connection_config):

        super(SQLConnection, self).__init__(connection_name, connection_config)

        self.dburi = None
        self.engine = None
        self.connection = None
        self.tables_established = False
        try:
            self.dburi = self.connection_config.get('dburi')
            self.engine = sqlalchemy.create_engine(self.dburi)
            self._migrate()
            self._setup_tables()
            self.tables_established = True
        except sqlalchemy.exc.NoSuchModuleError:
            self.log.exception(
                "The required module for the dburi dialect isn't available. "
                "SQL connection %s will be unavailable." % connection_name)
        except sqlalchemy.exc.OperationalError:
            self.log.exception(
                "Unable to connect to the database or establish the required "
                "tables. Reporter %s is disabled" % self)

    def _migrate(self):
        """Perform the alembic migrations for this connection"""
        with self.engine.begin() as conn:
            context = alembic.migration.MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            self.log.debug('Current migration revision: %s' % current_rev)

            config = alembic.config.Config()
            config.set_main_option("script_location",
                                   "zuul:alembic/sql_reporter")
            config.set_main_option("sqlalchemy.url",
                                   self.connection_config.get('dburi'))

            alembic.command.upgrade(config, 'head')

    def _setup_tables(self):
        metadata = sqlalchemy.MetaData()

        self.zuul_build = sqlalchemy.Table(
            BUILD_TABLE, metadata,
            sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column('uuid', sqlalchemy.String(255)),
            sqlalchemy.Column('job_name', sqlalchemy.String(255)),
            sqlalchemy.Column('score', sqlalchemy.Integer),
            sqlalchemy.Column('result', sqlalchemy.String(255)),
            sqlalchemy.Column('start_time', sqlalchemy.Integer),
            sqlalchemy.Column('end_time', sqlalchemy.Integer),
            sqlalchemy.Column('message', sqlalchemy.String(255)),
        )

        self.zuul_build_metadata = sqlalchemy.Table(
            BUILD_METADATA_TABLE, metadata,
            sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column('build_id', sqlalchemy.Integer,
                              sqlalchemy.ForeignKey(BUILD_TABLE + ".id")),
            sqlalchemy.Column('key', sqlalchemy.String(255)),
            sqlalchemy.Column('value', sqlalchemy.String(255)),
        )


def getSchema():
    sql_connection = v.Any(str, v.Schema({}, extra=True))
    return sql_connection
