# Copyright 2021 Acme Gating, LLC
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

import re
import subprocess

from zuul.driver.sql import SQLDriver
from tests.base import (
    BaseTestCase, MySQLSchemaFixture, PostgresqlSchemaFixture
)


class TestMysqlDatabase(BaseTestCase):
    def setUp(self):
        super().setUp()

        f = MySQLSchemaFixture()
        self.useFixture(f)

        config = dict(dburi=f.dburi)
        driver = SQLDriver()
        self.connection = driver.getConnection('database', config)
        self.connection.onLoad()
        self.addCleanup(self.connection.onStop)

    def compareMysql(self, alembic_text, sqlalchemy_text):
        alembic_lines = alembic_text.split('\n')
        sqlalchemy_lines = sqlalchemy_text.split('\n')
        self.assertEqual(len(alembic_lines), len(sqlalchemy_lines))
        alembic_constraints = []
        sqlalchemy_constraints = []
        for i in range(len(alembic_lines)):
            if alembic_lines[i].startswith("  `"):
                # Column
                self.assertEqual(alembic_lines[i], sqlalchemy_lines[i])
            elif alembic_lines[i].startswith("  "):
                # Constraints can be unordered
                # strip trailing commas since the last line omits it
                alembic_constraints.append(
                    re.sub(',$', '', alembic_lines[i]))
                sqlalchemy_constraints.append(
                    re.sub(',$', '', sqlalchemy_lines[i]))
            else:
                self.assertEqual(alembic_lines[i], sqlalchemy_lines[i])
        alembic_constraints.sort()
        sqlalchemy_constraints.sort()
        self.assertEqual(alembic_constraints, sqlalchemy_constraints)

    def test_migration(self):
        # Test that SQLAlchemy create_all produces the same output as
        # a full migration run.
        sqlalchemy_tables = {}
        self.connection.engine.execute("set foreign_key_checks=0")
        for table in self.connection.engine.execute("show tables"):
            table = table[0]
            sqlalchemy_tables[table] = self.connection.engine.execute(
                f"show create table {table}").one()[1]
            self.connection.engine.execute(f"drop table {table}")
        self.connection.engine.execute("set foreign_key_checks=1")
        self.connection.force_migrations = True
        self.connection.onStop()
        self.connection.onLoad()
        for table in self.connection.engine.execute("show tables"):
            table = table[0]
            create = self.connection.engine.execute(
                f"show create table {table}").one()[1]
            self.compareMysql(create, sqlalchemy_tables[table])


class TestPostgresqlDatabase(BaseTestCase):
    def setUp(self):
        super().setUp()

        f = PostgresqlSchemaFixture()
        self.useFixture(f)
        self.db = f

        config = dict(dburi=f.dburi)
        driver = SQLDriver()
        self.connection = driver.getConnection('database', config)
        self.connection.onLoad()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.connection.onStop()

    def test_migration(self):
        # Test that SQLAlchemy create_all produces the same output as
        # a full migration run.
        sqlalchemy_out = subprocess.check_output(
            f"pg_dump -h {self.db.host} -U {self.db.name} -s {self.db.name}",
            shell=True,
            env={'PGPASSWORD': self.db.passwd}
        )

        tables = [x[0] for x in self.connection.engine.execute(
            "select tablename from pg_catalog.pg_tables "
            "where schemaname='public'"
        ).all()]

        self.assertTrue(len(tables) > 0)
        for table in tables:
            self.connection.engine.execute(f"drop table {table} cascade")

        self.connection.force_migrations = True
        self.connection.onStop()
        self.connection.onLoad()

        alembic_out = subprocess.check_output(
            f"pg_dump -h {self.db.host} -U {self.db.name} -s {self.db.name}",
            shell=True,
            env={'PGPASSWORD': self.db.passwd}
        )
        self.assertEqual(alembic_out, sqlalchemy_out)
