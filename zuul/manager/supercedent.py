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

from zuul import model
from zuul.manager import PipelineManager, DynamicChangeQueueContextManager


class SupercedentPipelineManager(PipelineManager):
    """PipelineManager with one queue per project and a window of 1"""

    changes_merge = False

    def _postConfig(self, layout):
        super(SupercedentPipelineManager, self)._postConfig(layout)
        self.buildChangeQueues()

    def buildChangeQueues(self):
        self.log.debug("Building change queues")
        change_queues = {}
        layout = self.pipeline.layout
        layout_project_configs = layout.project_configs
        tenant = layout.tenant

        for project_name, project_configs in layout_project_configs.items():
            (trusted, project) = tenant.getProject(project_name)
            queue_name = None
            project_in_pipeline = False
            for project_config in layout.getAllProjectConfigs(project_name):
                project_pipeline_config = project_config.pipelines.get(
                    self.pipeline.name)
                if project_pipeline_config is None:
                    continue
                project_in_pipeline = True
            if not project_in_pipeline:
                continue
            p = self.pipeline
            change_queue = model.ChangeQueue(
                p,
                window=1,
                window_floor=1,
                window_increase_type='none',
                window_decrease_type='none')
            self.pipeline.addQueue(change_queue)
            self.log.debug("Created queue: %s" % change_queue)
            change_queue.addProject(project)
            self.log.debug("Added project %s to queue: %s" %
                           (project, change_queue))

    def getChangeQueue(self, change, existing=None):
        if existing:
            return StaticChangeQueueContextManager(existing)
        queue = self.pipeline.getQueue(change.project)
        if queue:
            return StaticChangeQueueContextManager(queue)
        else:
            # There is no existing queue for this change. Create a
            # dynamic one for this one change's use
            change_queue = model.ChangeQueue(self.pipeline, dynamic=True)
            change_queue.addProject(change.project)
            self.pipeline.addQueue(change_queue)
            self.log.debug("Dynamically created queue %s", change_queue)
            return DynamicChangeQueueContextManager(change_queue)

    def _pruneQueues(self):
        for queue in self.pipeline.queues:
            remove = queue.queue[1:-1]
            for item in remove:
                self.log.debug("Item %s is superceded by %s, removing" %
                               (item, queue.queue[:-1]))
                self.removeItem(item)

    def addChange(self, *args, **kw):
        self.log.debug("Considering adding change %s" % change)
        ret = super(SupercedentPipelineManager, self).addChange(
            *args, **kw)
        if ret:
            self._pruneQueues()
        return ret

    def dequeueItem(self, item):
        super(SupercedentPipelineManager, self).dequeueItem(item)
        # If this was a dynamic queue from a speculative change,
        # remove the queue (if empty)
        if item.queue.dynamic:
            if not item.queue.queue:
                self.pipeline.removeQueue(item.queue)
