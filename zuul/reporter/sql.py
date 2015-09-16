# Copyright 2015 Rackspace Australia
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

from zuul.reporter import BaseReporter


class SQLReporter(BaseReporter):
    """Sends off reports to Gerrit."""

    name = 'sql'
    log = logging.getLogger("zuul.SQLReporter")

    def __init__(self, reporter_config={}, sched=None, connection=None):
        super(SQLReporter, self).__init__(
            reporter_config, sched, connection)
        self.build_table = reporter_config.get('build_table', 'zuul_build')
        self.metadata_table = reporter_config.get(
            'build_metadata_table', 'zuul_build_metadata')
        self.result_score = reporter_config.get('score', None)
        self.tables_established = False
        self._setup_tables()

    def _setup_tables(self):
        """Create the tables for the results if they don't already exist"""
        try:
            if not self.connection.engine:
                self.log.warn("SQL connection not available to set up tables")
                return

            metadata = sqlalchemy.MetaData(self.connection.connect())

            self.zuul_build = sqlalchemy.Table(
                self.build_table, metadata,
                sqlalchemy.Column('uuid', sqlalchemy.String, primary_key=True),
                sqlalchemy.Column('job_name', sqlalchemy.String),
                sqlalchemy.Column('score', sqlalchemy.Integer),
                sqlalchemy.Column('result', sqlalchemy.String),
                sqlalchemy.Column('start_time', sqlalchemy.Integer),
                sqlalchemy.Column('end_time', sqlalchemy.Integer),
                sqlalchemy.Column('message', sqlalchemy.String),
            )

            self.zuul_build_metadata = sqlalchemy.Table(
                self.metadata_table, metadata,
                sqlalchemy.Column(
                    'build_uuid', None,
                    sqlalchemy.ForeignKey(self.build_table + '.uuid')),
                sqlalchemy.Column('key', sqlalchemy.String),
                sqlalchemy.Column('value', sqlalchemy.String),
                sqlalchemy.UniqueConstraint('build_uuid', 'key',
                                            name='zuul_build_build_uuid_key'),
            )

            metadata.create_all()
            self.tables_established = True
        except sqlalchemy.exc.OperationalError:
            self.log.exception(
                "Unable to connect to the database or establish the required "
                "tables. Reporter %s is disabled" % self)

    def report(self, source, pipeline, item, message=None, params=[]):
        """Create an entry into a database."""

        if not self.tables_established:
            self.log.warn("SQL reporter (%s) is disabled " % self)
            return

        build_inserts = []
        metadata_inserts = []
        for job in pipeline.getJobs(item):
            build = item.current_build_set.getBuild(job.name)
            if not build:
                # build hasn't began. The sql reporter can only send back stats
                # about builds. It doesn't understand how to store information
                # about the change.
                continue
            result = build.result
            url = self._createBuildURL(pipeline, job, item)
            build_inserts.append({
                'uuid': build.uuid,
                'job_name': job.name,
                'result': result,
                'score': self.result_score,
                'start_time': build.start_time,
                'end_time': build.end_time,
                'message': message,
            })
            # TODO(jhesketh): Add more metadata here
            metadata_inserts.append({
                'build_uuid': build.uuid,
                'key': 'changeid',
                'value': '%s,%s' % (item.change.number, item.change.patchset),
            })
            metadata_inserts.append({
                'build_uuid': build.uuid,
                'key': 'url',
                'value': url,
            })

        conn = self.connection.connect()
        conn.execute(self.zuul_build.insert(), build_inserts)
        conn.execute(self.zuul_build_metadata.insert(), metadata_inserts)


def getSchema():
    sql_reporter = v.Schema({
        'score': int,
        'build_table': str,
        'build_metadata_table': str,
    })
    return sql_reporter
