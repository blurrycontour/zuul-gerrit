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

import logging

from zuul.model import MergeRequest
from zuul.zk.job_request_queue import JobRequestQueue

import mmh3


def merger_score(name, request):
    return mmh3.hash(f"{name}-{request.uuid}", signed=False)


class MergerApi(JobRequestQueue):
    log = logging.getLogger("zuul.MergerApi")
    request_class = MergeRequest

    def __init__(self, client,
                 component_registry=None,
                 component_info=None,
                 use_cache=True,
                 merge_request_callback=None):
        root = '/zuul/merger'
        self.component_registry = component_registry
        self.component_info = component_info
        super().__init__(client, root, use_cache, merge_request_callback)

    def _getMergers(self):
        mergers = set(
            [m.hostname for m in self.component_registry.all("merger")
             if m.state == m.RUNNING]
        ).union(
            [e.hostname for e in self.component_registry.all("executor")
             if e.state == e.RUNNING and e.process_merge_jobs]
        )
        # If someone takes the unusual step of running a standalone
        # merger on the same host as an executor that accepts merge
        # jobs, they will have two mergers with the same name.  Both
        # will attempt to run each job and the locks will sort out the
        # winner.  Since this is not an expected configuration in a
        # system at scale, we don't optimize for it by disambiguating
        # the names here.
        return mergers

    def next(self):
        candidate_names = self._getMergers()
        if not candidate_names:
            return
        for request in self.inState(self.request_class.REQUESTED):
            scored_mergers = set(request.scores.keys())
            missing_scores = set(candidate_names) - scored_mergers
            if missing_scores:
                # (Re-)compute scores
                request.scores = {merger_score(n, request): n
                                  for n in candidate_names}
            merger_scores = sorted(request.scores.items())
            if merger_scores[0][1] != self.component_info.hostname:
                # Only yield if we're the first
                continue
            # Double check that it's still valid
            request = self.cache.getRequest(request.uuid)
            if (request and
                request.state == self.request_class.REQUESTED and
                not request.is_locked):
                yield request
