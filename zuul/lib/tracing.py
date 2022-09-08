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

import grpc
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
    OTLPSpanExporter as GRPCExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
    OTLPSpanExporter as HTTPExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry import trace as trace_api
from opentelemetry.sdk import trace as trace_sdk

from zuul.lib.config import get_default, any_to_bool


class ZuulSpan(Span):
    """An implementation of Span which accepts floating point
    times and converts them to the expected nanoseconds."""

    def start(self, start_time=None, parent_context=None):
        if isinstance(start_time, float):
            start_time = int(start_time * (10**9))
        return super().start(start_time, parent_context)

    def end(self, end_time=None):
        if isinstance(end_time, float):
            end_time = int(end_time * (10**9))
        return super().end(end_time)


# Patch the OpenTelemetry SDK Span class to return a ZuulSpan so that
# we can supply floating point timestamps.
trace_sdk._Span = ZuulSpan


def _formatContext(context):
    return {
        'trace_id': context.trace_id,
        'span_id': context.span_id,
    }


def _formatAttributes(attrs):
    if attrs is None:
        return None
    return attrs.copy()


class Tracing:
    PROTOCOL_GRPC = 'grpc'
    PROTOCOL_HTTP_PROTOBUF = 'http/protobuf'
    processor_class = BatchSpanProcessor

    def __init__(self, config):
        service_name = get_default(config, "tracing", "service_name", "zuul")
        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        enabled = get_default(config, "tracing", "enabled")
        if not any_to_bool(enabled):
            self.processor = None
            self.tracer = provider.get_tracer("zuul")
            return

        protocol = get_default(config, "tracing", "protocol",
                               self.PROTOCOL_GRPC)
        endpoint = get_default(config, "tracing", "endpoint")
        tls_key = get_default(config, "tracing", "tls_key")
        tls_cert = get_default(config, "tracing", "tls_cert")
        tls_ca = get_default(config, "tracing", "tls_ca")
        certificate_file = get_default(config, "tracing", "certificate_file")
        insecure = get_default(config, "tracing", "insecure")
        if insecure is not None:
            insecure = any_to_bool(insecure)
        timeout = get_default(config, "tracing", "timeout")
        if timeout is not None:
            timeout = int(timeout)
        compression = get_default(config, "tracing", "compression")

        if protocol == self.PROTOCOL_GRPC:
            if certificate_file:
                raise Exception("The certificate_file tracing option "
                                f"is not valid for {protocol} endpoints")
            if any([tls_ca, tls_key, tls_cert]):
                if tls_ca:
                    tls_ca = open(tls_ca, 'rb').read()
                if tls_key:
                    tls_key = open(tls_key, 'rb').read()
                if tls_cert:
                    tls_cert = open(tls_cert, 'rb').read()
                creds = grpc.ssl_channel_credentials(
                    root_certificates=tls_ca,
                    private_key=tls_key,
                    certificate_chain=tls_cert)
            else:
                creds = None
            exporter = GRPCExporter(
                endpoint=endpoint,
                insecure=insecure,
                credentials=creds,
                timeout=timeout,
                compression=compression)
        elif protocol == self.PROTOCOL_HTTP_PROTOBUF:
            if insecure:
                raise Exception("The insecure tracing option "
                                f"is not valid for {protocol} endpoints")
            if any([tls_ca, tls_key, tls_cert]):
                raise Exception("The tls_* tracing options "
                                f"are not valid for {protocol} endpoints")
            exporter = HTTPExporter(
                endpoint=endpoint,
                certificate_file=certificate_file,
                timeout=timeout,
                compression=compression)
        else:
            raise Exception(f"Unknown tracing protocol {protocol}")
        self.processor = self.processor_class(exporter)
        provider.add_span_processor(self.processor)
        self.tracer = provider.get_tracer("zuul")

    def stop(self):
        if not self.processor:
            return
        self.processor.shutdown()

    def getSpanInfo(self, span):
        """Return a dict for use in serializing a Span."""
        links = [{'context': _formatContext(l.context),
                  'attributes': _formatAttributes(l.attributes)}
                 for l in span.links]
        attrs = _formatAttributes(span.attributes)
        ret = {
            'name': span.name,
            'trace_id': span.context.trace_id,
            'span_id': span.context.span_id,
            'trace_flags': span.context.trace_flags,
            'start_time': span.start_time,
        }
        if links:
            ret['links'] = links
        if attrs:
            ret['attributes'] = attrs
        return ret

    @staticmethod
    def getSpanContext(span):
        """Return a dict for use in serializing a Span Context.

        The span context information used here is a lightweight
        encoding of the span information so that remote child spans
        can be started without access to a fully restored parent.
        This is equivalent to (but not the same format) as the
        OpenTelemetry trace context propogator.
        """
        ctx = span.get_span_context()
        return {
            'trace_id': ctx.trace_id,
            'span_id': ctx.span_id,
            'trace_flags': ctx.trace_flags,
        }
        return None

    def restoreSpan(self, span_info, is_remote=True):
        """Restore a Span from the serialized dict provided by getSpanInfo

        Return None if unable to serialize the span.
        """
        if span_info is None:
            return trace_api.INVALID_SPAN
        required_keys = {'name', 'trace_id', 'span_id', 'trace_flags'}
        if not required_keys <= set(span_info.keys()):
            return trace_api.INVALID_SPAN
        span_context = trace_api.SpanContext(
            span_info['trace_id'],
            span_info['span_id'],
            is_remote=is_remote,
            trace_flags=trace_api.TraceFlags(span_info['trace_flags']),
        )
        links = []
        for link_info in span_info.get('links', []):
            link_context = trace_api.SpanContext(
                link_info['context']['trace_id'],
                link_info['context']['span_id'])
            link = trace_api.Link(link_context, link_info['attributes'])
            links.append(link)
        attributes = span_info.get('attributes', {})

        span = ZuulSpan(
            name=span_info['name'],
            context=span_context,
            parent=None,
            sampler=self.tracer.sampler,
            resource=self.tracer.resource,
            attributes=attributes,
            span_processor=self.tracer.span_processor,
            kind=trace_api.SpanKind.INTERNAL,
            links=links,
            instrumentation_info=self.tracer.instrumentation_info,
            record_exception=False,
            set_status_on_exception=True,
            limits=self.tracer._span_limits,
            instrumentation_scope=self.tracer._instrumentation_scope,
        )
        span.start(start_time=span_info['start_time'])

        return span

    def useSpan(self, span):
        """Make a span the current span in the default tracing context

        This returns a context manager.  As long as the context
        manager is active, newly created spans will be part of the
        same trace as the provided span.
        """
        return trace_api.use_span(span)

    def startSpan(self, name, parent=None, **kw):
        """Start a span

        If no parent is supplied, this starts a new trace and root
        span, otherwise starts a child span of the parent.

        """
        if parent:
            with self.useSpan(parent):
                return self.tracer.start_span(name, **kw)
        else:
            return self.tracer.start_span(name, **kw)

    def startSavedSpan(self, *args, **kw):
        """Start a span and serialize it

        This is a convenience method which starts a span (either root
        or child) and immediately serializes it.

        Most spans in Zuul should use this method.
        """
        if not self.tracer:
            return None
        span = self.startSpan(*args, **kw)
        return self.getSpanInfo(span)

    def endSavedSpan(self, span_info, end_time=None):
        """End a saved span.

        This is a convenience method to restore a saved span and
        immediately end it.

        Most spans in Zuul should use this method.
        """
        span = self.restoreSpan(span_info, is_remote=False)
        if span:
            span.end(end_time=end_time)

    def startSpanInContext(self, name, span_context, **kw):
        """Start a span using remote context information from getSpanContext.

        This is a convenience method to start a child span of a remote
        parent span without fully restoring the parent span.
        """
        if span_context:
            span_context = trace_api.SpanContext(
                trace_id=span_context['trace_id'],
                span_id=span_context['span_id'],
                is_remote=True,
                trace_flags=trace_api.TraceFlags(span_context['trace_flags'])
            )
        else:
            span_context = trace_api.INVALID_SPAN_CONTEXT
        parent = trace_api.NonRecordingSpan(span_context)
        with self.useSpan(parent):
            return self.tracer.start_span(name, **kw)
