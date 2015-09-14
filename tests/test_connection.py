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
import os
import re
import sqlalchemy
import tempfile
import testtools

import zuul.connection.gerrit
import zuul.connection.sql

from tests.base import ZuulTestCase


def _get_reporter_from_connection_name(reporters, connection_name):
    # Reporters are placed into lists for each action they may exist in.
    # Search through the given list for the correct reporter by its conncetion
    # name
    for r in reporters:
        if r.connection.connection_name == connection_name:
            return r


class TestGerritConnection(testtools.TestCase):
    log = logging.getLogger("zuul.test_connection")

    def test_driver_name(self):
        self.assertEqual('gerrit',
                         zuul.connection.gerrit.GerritConnection.driver_name)


class TestSQLConnection(testtools.TestCase):
    log = logging.getLogger("zuul.test_connection")

    def test_driver_name(self):
        self.assertEqual(
            'sql',
            zuul.connection.sql.SQLConnection.driver_name
        )


class TestConnections(ZuulTestCase):
    def setup_config(self, config_file='zuul-connections-same-gerrit.conf'):
        super(TestConnections, self).setup_config(config_file)
        # Because tables for the sql reporter are created in a different thread
        # (due to the scheduler loading the appropriate reporters dynamically)
        # we are unable to use the sqlite:///:memory: database. Instead set up
        # a database location for each test run.
        for section_name in self.config.sections():
            con_match = re.match(r'^connection ([\'\"]?)(.*)(\1)$',
                                 section_name, re.I)
            if not con_match:
                continue

            if self.config.get(section_name, 'driver') == 'sql':
                if self.config.get(section_name, 'dburi') == '$TEMP_SQLITE$':
                    temp_db_dir = tempfile.mkdtemp()
                    temp_db = os.path.join(temp_db_dir, 'zuul.db')
                    self.config.set(section_name, 'dburi',
                                    'sqlite:///' + temp_db)

    def test_multiple_gerrit_connections(self):
        "Test multiple connections to the one gerrit"

        A = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_review_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]['approvals']), 1)
        self.assertEqual(A.patchsets[-1]['approvals'][0]['type'], 'VRFY')
        self.assertEqual(A.patchsets[-1]['approvals'][0]['value'], '1')
        self.assertEqual(A.patchsets[-1]['approvals'][0]['by']['username'],
                         'jenkins')

        B = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'B')
        self.worker.addFailTest('project-test2', B)
        self.fake_review_gerrit.addEvent(B.getPatchsetCreatedEvent(1))

        self.waitUntilSettled()

        self.assertEqual(len(B.patchsets[-1]['approvals']), 1)
        self.assertEqual(B.patchsets[-1]['approvals'][0]['type'], 'VRFY')
        self.assertEqual(B.patchsets[-1]['approvals'][0]['value'], '-1')
        self.assertEqual(B.patchsets[-1]['approvals'][0]['by']['username'],
                         'civoter')

    def _test_sql_tables_created(self, build_table=None, metadata_table=None):
        "Test the tables for storing results are created properly"
        if not build_table:
            build_table = 'zuul_build'
        if not metadata_table:
            metadata_table = 'zuul_build_metadata'

        insp = sqlalchemy.engine.reflection.Inspector(
            self.connections['resultsdb'].engine)

        self.assertEqual(7, len(insp.get_columns(build_table)))
        self.assertEqual(3, len(insp.get_columns(metadata_table)))
        self.assertEqual([{
            'column_names': ['build_uuid', 'key'],
            'name': 'zuul_build_build_uuid_key'}],
            insp.get_unique_constraints(metadata_table))

    def test_sql_tables_created(self):
        "Test the default table is created"
        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-sql-reporter.yaml')
        self.sched.reconfigure(self.config)
        self._test_sql_tables_created()

    def _test_sql_results(self):
        "Test results are entered into an sql table"
        # Grab the sqlalchemy tables
        reporter = _get_reporter_from_connection_name(
            self.sched.layout.pipelines['check'].success_actions,
            'resultsdb'
        )

        # Add a success result
        A = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_review_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Add a failed result for a negative score
        B = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'B')
        self.worker.addFailTest('project-test1', B)
        self.fake_review_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        conn = self.connections['resultsdb'].engine.connect()
        result = conn.execute(
            sqlalchemy.sql.select([reporter.connection.zuul_build]))

        rows = result.fetchall()
        self.assertEqual(6, len(rows))

        # Check the first result, which should be the project-merge job
        row = rows[0]
        metadata = conn.execute(
            sqlalchemy.sql.select([reporter.connection.zuul_build_metadata]).
            where(sqlalchemy.sql.and_(
                reporter.connection.zuul_build_metadata.c.build_uuid ==
                reporter.connection.zuul_build.c.uuid,
                reporter.connection.zuul_build_metadata.c.build_uuid ==
                row['uuid']))
        ).fetchall()
        metadata_dict = {}
        for data in metadata:
            metadata_dict[data['key']] = data['value']

        self.assertEqual('project-merge', row['job_name'])
        self.assertEqual("SUCCESS", row['result'])
        self.assertEqual(1, row['score'])
        self.assertEqual('1,1', metadata_dict['changeid'])
        self.assertEqual('http://logs.example.com/1/1/check/project-merge/0',
                         metadata_dict['url'])
        self.assertEqual(None, row['message'])

        # Check the second last result, which should be the project-test1 job
        # which failed
        row = rows[-2]
        metadata = conn.execute(
            sqlalchemy.sql.select([reporter.connection.zuul_build_metadata]).
            where(sqlalchemy.sql.and_(
                reporter.connection.zuul_build_metadata.c.build_uuid ==
                reporter.connection.zuul_build.c.uuid,
                reporter.connection.zuul_build_metadata.c.build_uuid ==
                row['uuid']))
        ).fetchall()
        metadata_dict = {}
        for data in metadata:
            metadata_dict[data['key']] = data['value']

        self.assertEqual('project-test1', row['job_name'])
        self.assertEqual("FAILURE", row['result'])
        self.assertEqual(-1, row['score'])
        self.assertEqual('2,1', metadata_dict['changeid'])
        self.assertEqual('http://logs.example.com/2/1/check/project-test1/4',
                         metadata_dict['url'])
        self.assertEqual(None, row['message'])

    def test_sql_results(self):
        "Test results are entered into the default sql table"
        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-sql-reporter.yaml')
        self.sched.reconfigure(self.config)
        self._test_sql_results()

    def notest_multiple_sql_connections(self):
        "Test putting results in different databases"
        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-sql-reporter.yaml')
        self.sched.reconfigure(self.config)

        # Add a successful result
        A = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_review_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Add a failed result
        B = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'B')
        self.worker.addFailTest('project-test1', B)
        self.fake_review_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Grab the sqlalchemy tables for resultsdb
        reporter1 = _get_reporter_from_connection_name(
            self.sched.layout.pipelines['check'].success_actions,
            'resultsdb'
        )

        conn = self.connections['resultsdb'].engine.connect()
        result = conn.execute(sqlalchemy.sql.select(
            [reporter1.connection.zuul_build]))
        # Should have been 6 jobs reported to the resultsdb
        self.assertEqual(6, len(result.fetchall()))

        # Grab the sqlalchemy tables for resultsdb_failures
        reporter2 = _get_reporter_from_connection_name(
            self.sched.layout.pipelines['check'].failure_actions,
            'resultsdb_failures'
        )

        conn = self.connections['resultsdb_failures'].engine.connect()
        result = conn.execute(sqlalchemy.sql.select(
            [reporter2.connection.zuul_build]))
        rows = result.fetchall()
        # The failure db should only have 3 jobs from the failed try
        self.assertEqual(3, len(rows))

        # Check the failed result
        found_failed_project = False
        for row in rows:
            if row['job_name'] == 'project-test1':
                found_failed_project = True
                self.assertEqual("FAILURE", row['result'])

        self.assertEqual(True, found_failed_project)


class TestConnectionsBadSQL(ZuulTestCase):
    def setup_config(self, config_file='zuul-connections-bad-sql.conf'):
        super(TestConnectionsBadSQL, self).setup_config(config_file)

    def test_unable_to_connect(self):
        "Test the SQL reporter fails gracefully when unable to connect"
        self.config.set('zuul', 'layout_config',
                        'tests/fixtures/layout-sql-reporter.yaml')
        self.sched.reconfigure(self.config)

        # Trigger a reporter. If no errors are raised, the reporter has been
        # disabled correctly
        A = self.fake_review_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_review_gerrit.addEvent(A.getPatchsetCreatedEvent(1))


class TestMultipleGerrits(ZuulTestCase):
    def setup_config(self,
                     config_file='zuul-connections-multiple-gerrits.conf'):
        super(TestMultipleGerrits, self).setup_config(config_file)
        self.config.set(
            'zuul', 'layout_config',
            'layout-connections-multiple-gerrits.yaml')

    def test_multiple_project_separate_gerrits(self):
        self.worker.hold_jobs_in_build = True

        A = self.fake_another_gerrit.addFakeChange(
            'org/project', 'master', 'A')
        self.fake_another_gerrit.addEvent(A.getPatchsetCreatedEvent(1))

        self.waitUntilSettled()

        self.assertEqual(1, len(self.builds))
        self.assertEqual('project-another-gerrit', self.builds[0].name)
        self.assertTrue(self.job_has_changes(self.builds[0], A))

        self.worker.hold_jobs_in_build = False
        self.worker.release()
        self.waitUntilSettled()
