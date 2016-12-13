# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
# Copyright 2016 Red Hat, Inc.
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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from zuul.model import TriggerEvent
import timertrigger


class TimerDriver(object):
    name = 'timer'

    log = logging.getLogger("zuul.Timer")

    def __init__(self):
        self.apsched = BackgroundScheduler()
        self.apsched.start()
        self.tenant_jobs = {}

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def reconfigure(self, tenant):
        self._removeJobs(tenant)
        self._addJobs(tenant)

    def _removeJobs(self, tenant):
        jobs = self.tenant_jobs.get(tenant.name, [])
        for job in jobs:
            job.remove()

    def _addJobs(self, tenant):
        jobs = []
        self.tenant_jobs[tenant.name] = jobs
        for pipeline in tenant.layout.pipelines:
            for ef in pipeline.manager.event_filters:
                if not isinstance(ef.trigger, timertrigger.TimerTrigger):
                    continue
                for timespec in ef.timespecs:
                    parts = timespec.split()
                    if len(parts) < 5 or len(parts) > 6:
                        self.log.error(
                            "Unable to parse time value '%s' "
                            "defined in pipeline %s" % (
                                timespec,
                                pipeline.name))
                        continue
                    minute, hour, dom, month, dow = parts[:5]
                    if len(parts) > 5:
                        second = parts[5]
                    else:
                        second = None
                    trigger = CronTrigger(day=dom, day_of_week=dow, hour=hour,
                                          minute=minute, second=second)

                    job = self.apsched.add_job(
                        self._onTrigger, trigger=trigger,
                        args=(tenant, pipeline.name, timespec,))
                    jobs.append(job)

    def _onTrigger(self, tenant, pipeline_name, timespec):
        for project in tenant.layout.projects.values():
            event = TriggerEvent()
            event.type = 'timer'
            event.timespec = timespec
            event.forced_pipeline = pipeline_name
            event.project_name = project.name
            self.log.debug("Adding event %s" % event)
            self.sched.addEvent(event)

    def stop(self):
        self.apsched.shutdown()

    def getTrigger(self, connection_name):
        return timertrigger.TimerTrigger(self)

    def getTriggerSchema(self):
        return timertrigger.getSchema()
