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
from zuul.manager import PipelineManager, StaticChangeQueueContextManager
from zuul.manager import DynamicChangeQueueContextManager
from zuul.manager.shared import SharedQueuePipelineManager


class SerialPipelineManager(SharedQueuePipelineManager):
    """PipelineManager with shared queues and a window of 1"""

    changes_merge = False

    def dequeueItem(self, item):
        super(SerialPipelineManager, self).dequeueItem(item)
        # If this was a dynamic queue from a speculative change,
        # remove the queue (if empty)
        if item.queue.dynamic:
            if not item.queue.queue:
                self.pipeline.removeQueue(item.queue)
