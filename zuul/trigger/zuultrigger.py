# Copyright 2012-2014 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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
from zuul.model import EventFilter, TriggerEvent
from zuul.trigger import BaseTrigger


class ZuulTrigger(BaseTrigger):
    name = 'zuul'
    log = logging.getLogger("zuul.ZuulTrigger")

    def __init__(self):
        self._handle_parent_change_enqueued_events = False
        self._handle_project_change_merged_events = False

    def stop(self):
        pass

    def getEventFilters(self, trigger_conf):
        def toList(item):
            if not item:
                return []
            if isinstance(item, list):
                return item
            return [item]

        efilters = []
        if 'zuul' in trigger_conf:
            for trigger in toList(trigger_conf['zuul']):
                f = EventFilter(
                    trigger=self,
                    types=toList(trigger['event']),
                    pipelines=toList(trigger.get('pipeline')),
                    required_any_approval=(
                        toList(trigger.get('require-any-approval'))
                        + toList(trigger.get('require-approval'))
                    ),
                    required_all_approvals=toList(
                        trigger.get('require-all-approvals')
                    ),
                )
                efilters.append(f)

        return efilters

    def onChangeMerged(self, change):
        # Called each time zuul merges a change
        if self._handle_project_change_merged_events:
            try:
                self._createProjectChangeMergedEvents(change)
            except Exception:
                self.log.exception(
                    "Unable to create project-change-merged events for "
                    "%s" % (change,))

    def onChangeEnqueued(self, change, pipeline):
        # Called each time a change is enqueued in a pipeline
        if self._handle_parent_change_enqueued_events:
            try:
                self._createParentChangeEnqueuedEvents(change, pipeline)
            except Exception:
                self.log.exception(
                    "Unable to create parent-change-enqueued events for "
                    "%s in %s" % (change, pipeline))

    def _createProjectChangeMergedEvents(self, change):
        changes = self.source.getProjectOpenChanges(
            change.project)
        for open_change in changes:
            self._createProjectChangeMergedEvent(open_change)

    def _createProjectChangeMergedEvent(self, change):
        event = TriggerEvent()
        event.type = 'project-change-merged'
        event.trigger_name = self.name
        event.project_name = change.project.name
        event.change_number = change.number
        event.branch = change.branch
        event.change_url = change.url
        event.patch_number = change.patchset
        event.refspec = change.refspec
        self.sched.addEvent(event)

    def _createParentChangeEnqueuedEvents(self, change, pipeline):
        self.log.debug("Checking for changes needing %s:" % change)
        if not hasattr(change, 'needed_by_changes'):
            self.log.debug("  Changeish does not support dependencies")
            return
        for needs in change.needed_by_changes:
            self._createParentChangeEnqueuedEvent(needs, pipeline)

    def _createParentChangeEnqueuedEvent(self, change, pipeline):
        event = TriggerEvent()
        event.type = 'parent-change-enqueued'
        event.trigger_name = self.name
        event.pipeline_name = pipeline.name
        event.project_name = change.project.name
        event.change_number = change.number
        event.branch = change.branch
        event.change_url = change.url
        event.patch_number = change.patchset
        event.refspec = change.refspec
        self.sched.addEvent(event)

    def postConfig(self):
        self._handle_parent_change_enqueued_events = False
        self._handle_project_change_merged_events = False
        for pipeline in self.sched.layout.pipelines.values():
            for ef in pipeline.manager.event_filters:
                if ef.trigger != self:
                    continue
                if 'parent-change-enqueued' in ef._types:
                    self._handle_parent_change_enqueued_events = True
                elif 'project-change-merged' in ef._types:
                    self._handle_project_change_merged_events = True
