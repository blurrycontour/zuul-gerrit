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

import datetime
import json
import logging
import time
import voluptuous as v

from zuul.lib.result_data import get_artifacts_from_result_data
from zuul.reporter import BaseReporter


class SQLReporter(BaseReporter):
    """Sends off reports to a database."""

    name = 'sql'
    log = logging.getLogger("zuul.SQLReporter")

    def _getBuildData(self, item, job, build):
        (result, _) = item.formatJobResult(job, build)
        start = end = None
        if build.start_time:
            start = datetime.datetime.fromtimestamp(
                build.start_time,
                tz=datetime.timezone.utc)
        if build.end_time:
            end = datetime.datetime.fromtimestamp(
                build.end_time,
                tz=datetime.timezone.utc)
        return result, build.log_url, start, end

    def createBuildEntry(self, item, job, db_buildset, build, final=True):
        # Ensure end_time is defined
        if not build.end_time:
            build.end_time = time.time()

        result, log_url, start, end = self._getBuildData(item, job, build)
        db_build = db_buildset.createBuild(
            uuid=build.uuid,
            job_name=build.job.name,
            result=result,
            start_time=start,
            end_time=end,
            voting=build.job.voting,
            log_url=log_url,
            nodeset=build.job.nodeset.name,
            error_detail=build.error_detail,
            final=final,
            held=build.held,
        )

        return db_build

    def reportBuildsetStart(self, buildset):
        """Create the initial buildset entry in the db"""
        if not buildset.uuid:
            return
        event_id = None
        item = buildset.item
        if item.event is not None:
            event_id = getattr(item.event, "zuul_event_id", None)

        with self.connection.getSession() as db:
            db_buildset = db.createBuildSet(
                uuid=buildset.uuid,
                tenant=item.pipeline.tenant.name,
                pipeline=item.pipeline.name,
                project=item.change.project.name,
                change=getattr(item.change, 'number', None),
                patchset=getattr(item.change, 'patchset', None),
                ref=getattr(item.change, 'ref', ''),
                oldrev=getattr(item.change, 'oldrev', ''),
                newrev=getattr(item.change, 'newrev', ''),
                branch=getattr(item.change, 'branch', ''),
                zuul_ref=buildset.ref,
                ref_url=item.change.url,
                event_id=event_id,
            )
            return db_buildset

    def reportBuildsetEnd(self, buildset, action, final, result=None):
        if not buildset.uuid:
            return
        if final:
            message = self._formatItemReport(
                buildset.item, with_jobs=False, action=action)
        else:
            message = None
        with self.connection.getSession() as db:
            db_buildset = db.getBuildset(
                tenant=buildset.item.pipeline.tenant.name, uuid=buildset.uuid)
            if db_buildset:
                db_buildset.result = buildset.result or result
                db_buildset.message = message
            elif buildset.builds:
                self.log.error("Unable to find buildset "
                               f"{buildset.uuid} in DB")

    def reportBuildStart(self, build):
        buildset = build.build_set
        start_time = build.start_time or time.time()
        start = datetime.datetime.fromtimestamp(start_time,
                                                tz=datetime.timezone.utc)
        with self.connection.getSession() as db:
            db_buildset = db.getBuildset(
                tenant=buildset.item.pipeline.tenant.name, uuid=buildset.uuid)

            db_build = db_buildset.createBuild(
                uuid=build.uuid,
                job_name=build.job.name,
                start_time=start,
                voting=build.job.voting,
                nodeset=build.job.nodeset.name,
            )
        return db_build

    def reportBuildEnd(self, build, final):
        end_time = build.end_time or time.time()
        end = datetime.datetime.fromtimestamp(end_time,
                                              tz=datetime.timezone.utc)
        with self.connection.getSession() as db:
            db_build = db.getBuild(
                tenant=build.build_set.item.pipeline.tenant.name,
                uuid=build.uuid)
            if not db_build:
                return None

            db_build.result = build.result
            db_build.end_time = end
            db_build.log_url = build.log_url
            db_build.error_detail = build.error_detail
            db_build.final = final
            db_build.held = build.held

            for provides in build.job.provides:
                db_build.createProvides(name=provides)

            for artifact in get_artifacts_from_result_data(
                build.result_data,
                logger=self.log):
                if 'metadata' in artifact:
                    artifact['metadata'] = json.dumps(artifact['metadata'])
                db_build.createArtifact(**artifact)

        return db_build

    # TODO: remove
    def report(self, item):
        """Create an entry into a database."""
        event_id = None
        if item.event is not None:
            event_id = getattr(item.event, "zuul_event_id", None)

        with self.connection.getSession() as db:
            db_buildset = db.createBuildSet(
                uuid=item.current_build_set.uuid,
                tenant=item.pipeline.tenant.name,
                pipeline=item.pipeline.name,
                project=item.change.project.name,
                change=getattr(item.change, 'number', None),
                patchset=getattr(item.change, 'patchset', None),
                ref=getattr(item.change, 'ref', ''),
                oldrev=getattr(item.change, 'oldrev', ''),
                newrev=getattr(item.change, 'newrev', ''),
                branch=getattr(item.change, 'branch', ''),
                zuul_ref=item.current_build_set.ref,
                ref_url=item.change.url,
                result=item.current_build_set.result,
                event_id=event_id,
                message=self._formatItemReport(item, with_jobs=False),
            )
            for job in item.getJobs():
                build = item.current_build_set.getBuild(job.name)
                if not build:
                    # build hasn't begun. The sql reporter can only send back
                    # stats about builds. It doesn't understand how to store
                    # information about the change.
                    continue
                retry_builds = item.current_build_set.getRetryBuildsForJob(
                    job.name
                )
                for retry_build in retry_builds:
                    self.createBuildEntry(
                        item, job, db_buildset, retry_build, final=False
                    )

                db_build = self.createBuildEntry(item, job, db_buildset, build)

                for provides in job.provides:
                    db_build.createProvides(name=provides)

                for artifact in get_artifacts_from_result_data(
                    build.result_data,
                    logger=self.log):
                    if 'metadata' in artifact:
                        artifact['metadata'] = json.dumps(artifact['metadata'])
                    db_build.createArtifact(**artifact)


def getSchema():
    sql_reporter = v.Schema(None)
    return sql_reporter
