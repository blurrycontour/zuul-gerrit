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

import time

from tests.base import iterate_timeout, ZuulTestCase

from opentelemetry import trace as trace_api


def attributes_to_dict(attrlist):
    ret = {}
    for attr in attrlist:
        ret[attr.key] = attr.value.string_value
    return ret


class TestTracing(ZuulTestCase):
    config_file = 'zuul-tracing.conf'
    tenant_config_file = "config/single-tenant/main.yaml"

    def test_tracing_api(self):
        tr = self.scheds.first.sched.tracing

        # We have a lot of timestamps stored as floats, so make sure
        # our root span is a ZuulSpan that can handle that input.
        span_info = tr.startSavedSpan('parent-trace', start_time=time.time())

        # Simulate a reconstructed root span
        span = tr.restoreSpan(span_info)

        # Within the root span, use the more typical OpenTelemetry
        # context manager api.
        with trace_api.use_span(span):
            with tr.tracer.start_span('child1-trace'):
                pass

        # Make sure that we can manually start and stop a child span,
        # and that it is a ZuulSpan as well.
        child = tr.startSpan('child2-trace', span, start_time=time.time())
        child.end(end_time=time.time())

        # End our root span manually.
        span.end(end_time=time.time())

        for _ in iterate_timeout(60, "request to arrive"):
            if len(self.otlp.requests) == 3:
                break
        req1 = self.otlp.requests[0]
        self.log.debug("Received:\n%s", req1)
        attrs = attributes_to_dict(req1.resource_spans[0].resource.attributes)
        self.assertEqual({"service.name": "zuultest"}, attrs)
        self.assertEqual("zuul",
                         req1.resource_spans[0].scope_spans[0].scope.name)
        span1 = req1.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("child1-trace", span1.name)

        req2 = self.otlp.requests[1]
        self.log.debug("Received:\n%s", req2)
        span2 = req2.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("child2-trace", span2.name)

        req3 = self.otlp.requests[2]
        self.log.debug("Received:\n%s", req3)
        span3 = req3.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("parent-trace", span3.name)

        self.assertEqual(span1.trace_id, span3.trace_id)
        self.assertEqual(span2.trace_id, span3.trace_id)

    def test_tracing(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        for _ in iterate_timeout(60, "request to arrive"):
            if len(self.otlp.requests) >= 2:
                break

        buildset = self.getSpan('BuildSet')
        item = self.getSpan('QueueItem')
        self.assertEqual(item.trace_id, buildset.trace_id)
        self.assertNotEqual(item.span_id, buildset.span_id)
        self.assertTrue(buildset.start_time_unix_nano >=
                        item.start_time_unix_nano)
        self.assertTrue(buildset.end_time_unix_nano <=
                        item.end_time_unix_nano)

    def getSpan(self, name):
        for req in self.otlp.requests:
            span = req.resource_spans[0].scope_spans[0].spans[0]
            if span.name == name:
                return span
