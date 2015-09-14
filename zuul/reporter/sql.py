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
import voluptuous as v

from zuul.reporter import BaseReporter


class SQLReporter(BaseReporter):
    """Sends off reports to a database."""

    name = 'sql'
    log = logging.getLogger("zuul.reporter.mysql.SQLReporter")

    def __init__(self, reporter_config={}, sched=None, connection=None):
        super(SQLReporter, self).__init__(
            reporter_config, sched, connection)
        self.result_score = reporter_config.get('score', None)

    def report(self, source, pipeline, item, message=None, params=[]):
        """Create an entry into a database."""

        if not self.connection.tables_established:
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

        with self.connection.engine.begin() as conn:
            conn.execute(self.connection.zuul_build.insert(), build_inserts)
            conn.execute(self.connection.zuul_build_metadata.insert(),
                         metadata_inserts)


def getSchema():
    sql_reporter = v.Schema({
        'score': int,
    })
    return sql_reporter
