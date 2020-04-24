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
from zuul.lib.logutil import get_annotated_logger
from zuul.manager import PipelineManager, DynamicChangeQueueContextManager


class SerialPipelineManager(PipelineManager):
    """PipelineManager with one queue per project and a window of 1"""

    changes_merge = False

    def getChangeQueue(self, change, event, existing=None):
        log = get_annotated_logger(self.log, event)

        # creates a new change queue for every project-ref
        # combination.
        if existing:
            return DynamicChangeQueueContextManager(existing)

        # Don't use Pipeline.getQueue to find an existing queue
        # because we're matching project and (branch or ref).
        for queue in self.pipeline.queues:
            if (queue.queue[-1].change.project == change.project and
                ((hasattr(change, 'branch') and
                  hasattr(queue.queue[-1].change, 'branch') and
                  queue.queue[-1].change.branch == change.branch) or
                queue.queue[-1].change.ref == change.ref)):
                log.debug("Found existing queue %s", queue)
                return DynamicChangeQueueContextManager(queue)
        change_queue = model.ChangeQueue(
            self.pipeline,
            window=1,
            window_floor=1,
            window_increase_type='none',
            window_decrease_type='none')
        change_queue.addProject(change.project)
        self.pipeline.addQueue(change_queue)
        log.debug("Dynamically created queue %s", change_queue)
        return DynamicChangeQueueContextManager(change_queue)

    def dequeueItem(self, item):
        super(SerialPipelineManager, self).dequeueItem(item)
        # A serial pipeline manager dynamically removes empty
        # queues
        if not item.queue.queue:
            self.pipeline.removeQueue(item.queue)
