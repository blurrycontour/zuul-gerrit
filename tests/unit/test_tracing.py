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
        span_info = tr.startSavedSpan('parent-trace', start_time=time.time(),
                                      attributes={'foo': 'bar'})

        # Simulate a reconstructed root span
        span = tr.restoreSpan(span_info)

        # Within the root span, use the more typical OpenTelemetry
        # context manager api.
        with trace_api.use_span(span):
            with tr.tracer.start_span('child1-trace') as child1_span:
                link = trace_api.Link(child1_span.context,
                                      attributes={'relationship': 'prev'})

        # Make sure that we can manually start and stop a child span,
        # and that it is a ZuulSpan as well.
        child = tr.startSpan('child2-trace', span, start_time=time.time(),
                             links=[link])
        child.end(end_time=time.time())

        # Make sure that we can start a child span from a span
        # context and not a full span:
        span_context = tr.getSpanContext(span)
        child = tr.startSpanInContext('child3-trace', span_context)
        child.end(end_time=time.time())

        # End our root span manually.
        span.end(end_time=time.time())

        for _ in iterate_timeout(60, "request to arrive"):
            if len(self.otlp.requests) == 4:
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
        self.assertEqual(span2.links[0].span_id, span1.span_id)
        attrs = attributes_to_dict(span2.links[0].attributes)
        self.assertEqual({"relationship": "prev"}, attrs)

        req3 = self.otlp.requests[2]
        self.log.debug("Received:\n%s", req3)
        span3 = req3.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("child3-trace", span3.name)

        req4 = self.otlp.requests[3]
        self.log.debug("Received:\n%s", req4)
        span4 = req4.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("parent-trace", span4.name)
        attrs = attributes_to_dict(span4.attributes)
        self.assertEqual({"foo": "bar"}, attrs)

        self.assertEqual(span1.trace_id, span4.trace_id)
        self.assertEqual(span2.trace_id, span4.trace_id)
        self.assertEqual(span3.trace_id, span4.trace_id)

    def test_tracing_api_null(self):
        tr = self.scheds.first.sched.tracing

        # Test that restoring spans and span contexts works with
        # null values.

        span_info = None
        # Simulate a reconstructed root span from a null value
        span = tr.restoreSpan(span_info)

        # Within the root span, use the more typical OpenTelemetry
        # context manager api.
        with trace_api.use_span(span):
            with tr.tracer.start_span('child1-trace') as child1_span:
                link = trace_api.Link(child1_span.context,
                                      attributes={'relationship': 'prev'})

        # Make sure that we can manually start and stop a child span,
        # and that it is a ZuulSpan as well.
        child = tr.startSpan('child2-trace', span, start_time=time.time(),
                             links=[link])
        child.end(end_time=time.time())

        # Make sure that we can start a child span from a null span
        # context:
        span_context = None
        child = tr.startSpanInContext('child3-trace', span_context)
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
        self.assertEqual(span2.links[0].span_id, span1.span_id)
        attrs = attributes_to_dict(span2.links[0].attributes)
        self.assertEqual({"relationship": "prev"}, attrs)

        req3 = self.otlp.requests[2]
        self.log.debug("Received:\n%s", req3)
        span3 = req3.resource_spans[0].scope_spans[0].spans[0]
        self.assertEqual("child3-trace", span3.name)

        self.assertNotEqual(span1.trace_id, span2.trace_id)
        self.assertNotEqual(span2.trace_id, span3.trace_id)
        self.assertNotEqual(span1.trace_id, span3.trace_id)

    def test_tracing(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        for _ in iterate_timeout(60, "request to arrive"):
            if len(self.otlp.requests) >= 2:
                break

        buildset = self.getSpan('BuildSet')
        self.log.debug("Received:\n%s", buildset)
        item = self.getSpan('QueueItem')
        self.log.debug("Received:\n%s", item)
        self.assertEqual(item.trace_id, buildset.trace_id)
        self.assertNotEqual(item.span_id, buildset.span_id)
        self.assertTrue(buildset.start_time_unix_nano >=
                        item.start_time_unix_nano)
        self.assertTrue(buildset.end_time_unix_nano <=
                        item.end_time_unix_nano)
        item_attrs = attributes_to_dict(item.attributes)
        self.assertTrue(item_attrs['ref_number'] == "1")
        self.assertTrue(item_attrs['ref_patchset'] == "1")
        self.assertTrue('zuul_event_id' in item_attrs)

    def getSpan(self, name):
        for req in self.otlp.requests:
            span = req.resource_spans[0].scope_spans[0].spans[0]
            if span.name == name:
                return span
