# Copyright (C) 2017 Red Hat
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

from pecan import conf
from pecan import expose
from pecan.rest import RestController
from sqlalchemy import create_engine
from sqlalchemy import orm
from sqlalchemy.sql import select
from zuul.driver.sql.sqlconnection import SQLConnection as ZuulSQL


class ZuulDashboardController(RestController):
    def __init__(self, dburi):
        super(ZuulDashboardController, self).__init__()
        self.engine = create_engine(dburi, echo=False, pool_recycle=600)
        Session = orm.sessionmaker(bind=self.engine)
        self.sql = Session()
        self.buildset, self.build = ZuulSQL._setup_tables()

    def jobInfo(self, job_name):
        """Return all the job executions information"""
        stm = select([
            self.build.c.id,
            self.buildset.c.pipeline,
            self.buildset.c.project,
            self.buildset.c.change,
            self.buildset.c.patchset,
            self.buildset.c.ref,
            self.buildset.c.score,
            self.build.c.start_time,
            self.build.c.end_time,
            self.build.c.log_url,
            self.build.c.node_name,
        ]).\
            where(self.build.c.job_name == job_name).\
            where(self.build.c.buildset_id == self.buildset.c.id)

        job = {'name': job_name, 'runs': []}
        for row in self.sql.execute(stm):
            run = dict(row)
            # Convert date to iso format
            run['start_time'] = row.start_time.strftime('%Y-%m-%dT%H:%M:%S')
            run['end_time'] = row.end_time.strftime('%Y-%m-%dT%H:%M:%S')
            # Compute run duration
            run['duration'] = (row.end_time - row.start_time).total_seconds()
            job['runs'].append(run)
        self.sql.commit()
        return job

    def jobLists(self):
        # Return list of job similar to jenkins dashboard
        jobs = {}
        for row in self.sql.execute(self.build.select()):
            name, end, result = row.job_name, row.end_time, row.result
            # Add new job to the list
            if name not in jobs:
                jobs[name] = {
                    'lastSuccess': end if result == 'SUCCESS' else None,
                    'lastFailure': end if result == 'FAILURE' else None,
                    'lastRun': end,
                    'lastStatus': result,
                    'lastDuration': end - row.start_time,
                    'count': 0
                }
            # Update job build information if relevant
            elif result == 'SUCCESS' and (not jobs[name]['lastSuccess'] or
                                          jobs[name]['lastSuccess'] < end):
                jobs[name]['lastSuccess'] = end
            elif result == 'FAILURE' and (not jobs[name]['lastFailure'] or
                                          jobs[name]['lastFailure'] < end):
                jobs[name]['lastFailure'] = end
            if jobs[name]['lastRun'] < end:
                jobs[name]['lastRun'] = end
                jobs[name]['lastStatus'] = result
            jobs[name]['count'] += 1
        self.sql.commit()

        jobs_list = []
        for job_name in sorted(jobs.keys()):
            job = jobs[job_name]
            jobs_list.append({
                'name': job_name,
                'status': job['lastStatus'],
                'count': job['count'],
                'lastSuccess': job['lastSuccess'].strftime(
                    '%Y-%m-%dT%H:%M:%S') if job['lastSuccess'] else None,
                'lastFailure': job['lastFailure'].strftime(
                    '%Y-%m-%dT%H:%M:%S') if job['lastFailure'] else None,
                'lastDuration': job['lastDuration'].total_seconds()})
        return jobs_list

    @expose('json')
    def index(self, job=None):
        if job is None:
            return self.jobLists()
        else:
            return self.jobInfo(job)


class RootController(object):
    zuul_dashboard = ZuulDashboardController(conf.zuul['dburi'])
