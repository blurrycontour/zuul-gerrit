# Copyright 2019 Red Hat, Inc.
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
import logging
import time
import voluptuous as v

from zuul.reporter import BaseReporter
from zuul.driver.elasticsearch.connection import EL_RESERVED_FIELDS


class ElasticsearchReporter(BaseReporter):
    name = 'elasticsearch'
    log = logging.getLogger("zuul.ElasticsearchReporter")

    def __init__(self, driver, connection, config):
        super(ElasticsearchReporter, self).__init__(driver, connection, config)
        job_vars_re = self.config.get('job_vars', [])
        self.vars_re = []
        for item in job_vars_re:
            try:
                re_c = re.compile(item)
            except Exception:
                pass
            self.vars_re.append(re_c)

    def _validate_data(self, key, value):
        if key in (
                EL_RESERVED_FIELDS +
                list(self.connection.properties.keys())):
            return False
        if (not isinstance(value, str) and
                not isinstance(value, int) and
                not isinstance(value, bool)):
            return False
        return True

    def _add_job_variables(self, doc, job, override):
        # Overwrite job variables by those returned in zuul_return
        job.variables.update(override)
        # Set matching variables into the doc
        for key, value in job.variables.items():
            if not self._validate_data(key, value):
                continue
            match = False
            for _re in self.vars_re:
                if _re.match(key):
                    match = True
                    break
            if match:
                doc["job_param.%s" % key] = str(value)

    def report(self, item):
        """Create an entry into a database."""
        docs = []
        buildset_doc = {
            "uuid": item.current_build_set.uuid,
            "build_type": "buildset",
            "tenant": item.pipeline.tenant.name,
            "pipeline": item.pipeline.name,
            "project": item.change.project.name,
            "change": getattr(item.change, 'number', None),
            "patchset": getattr(item.change, 'patchset', None),
            "ref": getattr(item.change, 'ref', ''),
            "oldrev": getattr(item.change, 'oldrev', ''),
            "newrev": getattr(item.change, 'newrev', ''),
            "branch": getattr(item.change, 'branch', ''),
            "zuul_ref": item.current_build_set.ref,
            "ref_url": item.change.url,
            "result": item.current_build_set.result,
            "message": self._formatItemReport(item, with_jobs=False)
        }

        for job in item.getJobs():
            build = item.current_build_set.getBuild(job.name)
            if not build:
                continue
            # Ensure end_time is defined
            if not build.end_time:
                build.end_time = time.time()
            # Ensure start_time is defined
            if not build.start_time:
                build.start_time = build.end_time

            (result, url) = item.formatJobResult(job)

            # Manage to set time attributes in buildset
            start_time = int(build.start_time)
            end_time = int(build.end_time)
            if ('start_time' not in buildset_doc or
                    buildset_doc['start_time'] > start_time):
                buildset_doc['start_time'] = start_time
            if ('end_time' not in buildset_doc or
                    buildset_doc['end_time'] < end_time):
                buildset_doc['end_time'] = end_time
            buildset_doc['duration'] = (
                buildset_doc['end_time'] - buildset_doc['start_time'])

            build_doc = {
                "uuid": build.uuid,
                "build_type": "build",
                "buildset_uuid": buildset_doc['uuid'],
                "job_name": build.job.name,
                "result": result,
                "start_time": str(start_time),
                "end_time": str(end_time),
                "duration": str(end_time - start_time),
                "voting": build.job.voting,
                "log_url": url,
                "node_name": build.node_name,
            }
            if self.vars_re:
                self._add_job_variables(
                    build_doc, job,
                    build.result_data.get('vars_override', {})
                )
            docs.append(build_doc)

        docs.append(buildset_doc)
        self.connection.add_docs(docs)


def getSchema():
    el_reporter = v.Schema(v.Any(None, dict))
    return el_reporter
