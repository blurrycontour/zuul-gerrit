# Copyright 2021 BMW Group
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

import json
import logging
import time
from contextlib import suppress

from kazoo.exceptions import LockTimeout, NoNodeError
from kazoo.protocol.states import EventType
from kazoo.recipe.lock import Lock

from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.model import MergeRequest
from zuul.zk.job_request_queue import JobRequestQueue


class MergerApi(JobRequestQueue):
    log = logging.getLogger("zuul.MergerApi")
    request_class = MergeRequest

    def __init__(self, client, merge_request_callback=None):
        root = '/zuul/merger'
        super().__init__(client, root, merge_request_callback)
