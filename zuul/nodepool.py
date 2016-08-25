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

from zuul.model import Node, NodeRequest


class Nodepool(object):
    def __init__(self, scheduler):
        self.requests = {}
        self.sched = scheduler

    def requestNodes(self, build_set, job):
        nodes = job.nodes.items()
        nodes = [Node(name, image) for (name, image) in nodes]
        req = NodeRequest(build_set, job, nodes)
        self.requests[req.id] = req
        self._requestComplete(req.id)
        return req

    def cancelRequest(self, request):
        if request in self.requests:
            self.requests.remove(request)

    def returnNodes(self, nodes, used=True):
        pass

    def _requestComplete(self, id):
        req = self.requests[id]
        del self.requests[id]
        self.sched.onNodesProvisioned(req)
