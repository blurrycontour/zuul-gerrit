# Copyright 2018 Red Hat
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
import uuid

import voluptuous

from zuul.driver import Driver, TriggerInterface
from zuul.model import Change, EventFilter, TriggerEvent, JobList
from zuul.trigger import BaseTrigger


class WebEventFilter(EventFilter):
    log = logging.getLogger("zuul.WebEventFilter")

    def matches(self, event, change):
        if change.type == "direct":
            return True
        return False


class WebTriggerChange(Change):
    def __init__(self, jobs):
        super().__init__("")
        self.jobs = jobs

        # TODO: support custom project and reference from args payload.
        class Project:
            name = ""
            canonical_name = ""
            canonical_hostname = ""
            source = ""
        self.number = str(uuid.uuid4()).split('-')[0]
        self.patchset = 1
        self.project = Project()
        self.branch = ""
        self.message = ""
        self.type = 'direct'

    def __repr__(self):
        return '<WebTriggerChange 0x%x %s>' % (id(self), self._id())


class WebTriggerEvent(TriggerEvent):
    """Manual job trigger event."""

    def __init__(self, tenant, args):
        super().__init__()
        jobs = JobList()

        job = tenant.layout.getJob(args['job']).copy()
        for k, v in args.get('variables', {}).items():
            job.variables[k] = v
        jobs.addJob(job)

        self.change = WebTriggerChange(jobs)

        # TODO: support custom project and reference from args payload.
        self.project_hostname = ""
        self.project_name = ""
        self.type = 'direct'
        self.ref = "refs/head/master"
        self.branch = "master"


class WebDriver(Driver, TriggerInterface):
    name = 'web'
    log = logging.getLogger("zuul.WebDriver")

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def getTrigger(self, connection_name, config=None):
        return WebTrigger(self, config)

    def getTriggerSchema(self):
        return voluptuous.Any(str, voluptuous.Schema(dict))

    def onEvent(self, tenant, args):
        self.sched.addEvent(WebTriggerEvent(tenant, args))


class WebTrigger(BaseTrigger):
    name = 'web'

    def getEventFilters(self, trigger_conf):
        return [WebEventFilter(self)]
