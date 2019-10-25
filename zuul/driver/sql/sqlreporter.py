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

    def reportBuildsetStart(self, buildset):
        """Create the initial buildset entry in the db"""
        if not buildset.uuid:
            return
        event_id = None
        item = buildset.item
        if item.event is not None:
            event_id = getattr(item.event, "zuul_event_id", None)

        # Provide a view of the current data to the async report call as the
        # buildset might change in the meantime.
        buildset_data = dict(
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

        self.connection.report_queue.put(
            (self, "BUILDSET_START", buildset_data))

    def _reportBuildsetStart(self, buildset_data):
        with self.connection.getSession() as db:
            db_buildset = db.createBuildSet(**buildset_data)
            return db_buildset

    def reportBuildsetEnd(self, buildset, action, final, result=None):
        if not buildset.uuid:
            return
        if final:
            message = self._formatItemReport(
                buildset.item, with_jobs=False, action=action)
        else:
            message = None

        # Provide a view of the current data to the async report call as the
        # buildset might change in the meantime.
        buildset_data = dict(
            tenant=buildset.item.pipeline.tenant.name,
            uuid=buildset.uuid,
            result=buildset.result or result,
            message=message,
            has_builds=bool(buildset.builds),
        )
        self.connection.report_queue.put((self, "BUILDSET_END", buildset_data))

    def _reportBuildsetEnd(self, buildset_data):
        with self.connection.getSession() as db:
            db_buildset = db.getBuildset(
                tenant=buildset_data["tenant"], uuid=buildset_data["uuid"])
            if db_buildset:
                db_buildset.result = buildset_data["result"]
                db_buildset.message = buildset_data["message"]
            elif buildset_data["has_builds"]:
                self.log.error("Unable to find buildset "
                               f"{buildset_data['uuid']} in DB")

    def reportBuildStart(self, build):
        buildset = build.build_set
        start_time = build.start_time or time.time()
        start = datetime.datetime.fromtimestamp(start_time,
                                                tz=datetime.timezone.utc)

        # Provide a view of the current data to the async report call as the
        # build might change in the meantime.
        build_data = dict(
            # TODO (felix): Provide the buildset related parameters
            # differently?
            buildset_uuid=buildset.uuid,
            tenant=buildset.item.pipeline.tenant.name,
            uuid=build.uuid,
            job_name=build.job.name,
            start_time=start,
            voting=build.job.voting,
            nodeset=build.job.nodeset.name,
        )
        self.connection.report_queue.put((self, "BUILD_START", build_data))

    def _reportBuildStart(self, build_data):
        tenant = build_data.pop("tenant")
        buildset_uuid = build_data.pop("buildset_uuid")

        with self.connection.getSession() as db:
            db_buildset = db.getBuildset(tenant=tenant, uuid=buildset_uuid)
            db_build = db_buildset.createBuild(**build_data)
        return db_build

    def reportBuildEnd(self, build, final):
        end_time = build.end_time or time.time()
        end = datetime.datetime.fromtimestamp(end_time,
                                              tz=datetime.timezone.utc)

        # Provide a view of the current data to the async report call as the
        # build might change in the meantime.
        build_data = dict(
            tenant=build.build_set.item.pipeline.tenant.name,
            uuid=build.uuid,
            result=build.result,
            end=end,
            log_url=build.log_url,
            error_detail=build.error_detail,
            final=final,
            held=build.held,
            provides=[p for p in build.job.provides],
            result_data=build.result_data,
        )

        self.connection.report_queue.put((self, "BUILD_END", build_data))

    def _reportBuildEnd(self, build_data):
        tenant = build_data.pop("tenant")
        uuid = build_data.pop("uuid")

        with self.connection.getSession() as db:
            db_build = db.getBuild(tenant=tenant, uuid=uuid)
            if not db_build:
                return None

            db_build.result = build_data["result"]
            db_build.end_time = build_data["end"]
            db_build.log_url = build_data["log_url"]
            db_build.error_detail = build_data["error_detail"]
            db_build.final = build_data["final"]
            db_build.held = build_data["held"]

            for provides in build_data["provides"]:
                db_build.createProvides(name=provides)

            for artifact in get_artifacts_from_result_data(
                build_data["result_data"],
                logger=self.log):
                if 'metadata' in artifact:
                    artifact['metadata'] = json.dumps(artifact['metadata'])
                db_build.createArtifact(**artifact)

        return db_build

    def report(self, item):
        # We're not a real reporter, but we use _formatItemReport, so
        # we inherit from the reporters.
        raise NotImplementedError()


def getSchema():
    sql_reporter = v.Schema(None)
    return sql_reporter
