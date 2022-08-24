# Copyright 2022 Acme Gating, LLC
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

from tests.base import iterate_timeout, ZuulTestCase


def attributes_to_dict(attrlist):
    ret = {}
    for attr in attrlist:
        ret[attr.key] = attr.value.string_value
    return ret


class TestTracing(ZuulTestCase):
    config_file = 'zuul-tracing.conf'
    tenant_config_file = "config/single-tenant/main.yaml"

    def test_tracing(self):
        self.scheds.first.sched.tracing.test()
        for _ in iterate_timeout(60, "request to arrive"):
            if self.otlp.requests:
                break
        req = self.otlp.requests[0]
        self.log.debug("Received:\n%s", req)
        attrs = attributes_to_dict(req.resource_spans[0].resource.attributes)
        self.assertEqual({"service.name": "zuultest"}, attrs)
        self.assertEqual("zuul",
                         req.resource_spans[0].scope_spans[0].scope.name)
        span = req.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("test-trace", span.name)
