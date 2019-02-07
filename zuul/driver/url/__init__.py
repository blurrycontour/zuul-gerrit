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
import requests

from zuul.driver.timer import TimerDriver
from zuul.driver.url import urltrigger
from zuul.driver.url.urlmodel import URLTriggerEvent


class URLDriver(TimerDriver):
    name = 'url'
    log = logging.getLogger("zuul.URLDriver")

    def __init__(self):
        super(URLDriver, self).__init__()
        self.url_cache = {}

    def _addJobs(self, tenant):
        jobs = []
        self.tenant_jobs[tenant.name] = jobs
        for pipeline in tenant.layout.pipelines.values():
            for ef in pipeline.manager.event_filters:
                if not isinstance(ef.trigger, urltrigger.URLTrigger):
                    continue
                try:
                    trigger = self._build_cron_trigger(ef.time)
                except Exception as exc:
                    self.log.error(
                        "Unable to set CronTrigger for pipeline %s: %s" % (
                            pipeline.name, exc))
                    continue
                try:
                    pfilter = re.compile(ef.pfilter)
                except Exception as exc:
                    self.log.error(
                        "Unable to compile project filter regexp '%s' "
                        "for pipeline %s: %s" % (
                            ef.pfilter, pipeline.name, exc)
                    )
                    continue
                self.url_cache[ef.url] = {ef.header_field: None}
                job = self.apsched.add_job(
                    self._onTrigger, trigger=trigger,
                    args=(tenant, pipeline.name, ef.time, ef.url,
                          ef.header_field, pfilter))
                jobs.append(job)

    def _onTrigger(
            self, tenant, pipeline_name, timespec, url, field, pfilter):
        for project_name, pcs in tenant.layout.project_configs.items():
            if not pfilter.match(project_name):
                continue

            pcst = tenant.layout.getAllProjectConfigs(project_name)
            if not [True for pc in pcst if pipeline_name in pc.pipelines]:
                continue

            self.log.debug("Fetching %s" % url)
            headers = requests.get(url).headers
            value = headers.get(field)
            if self.url_cache[url][field] is None:
                # New url - Only feed the cache
                self.log.debug(
                    "No previous state for %s only feed the cache for: %s" % (
                        field, url))
                self.url_cache[url][field] = value
                continue
            if value == self.url_cache[url][field]:
                self.log.debug("Field %s for %s has not changed" % (
                    field, url))
                continue
            self.log.info("Url status at %s changed" % url)
            self.url_cache[url][field] = value

            (trusted, project) = tenant.getProject(project_name)
            for branch in project.source.getProjectBranches(project, tenant):
                event = URLTriggerEvent()
                event.type = 'url'
                event.timespec = timespec
                event.forced_pipeline = pipeline_name
                event.project_hostname = project.canonical_hostname
                event.project_name = project.name
                event.ref = 'refs/heads/%s' % branch
                event.branch = branch
                self.log.debug("Adding event %s" % event)
                self.sched.addEvent(event)

    def getTrigger(self, connection_name, config=None):
        return urltrigger.URLTrigger(self, config)

    def getTriggerSchema(self):
        return urltrigger.getSchema()
