# Copyright 2020, BMW Group
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

import ast
import importlib
import logging
import re

from opentelemetry import trace
from opentelemetry.context.propagation.tracecontexthttptextformat import (
    TraceContextHTTPTextFormat,
)
from opentelemetry.sdk.trace import TracerSource
from opentelemetry.sdk.trace.export import (
    BatchExportSpanProcessor,
    ConsoleSpanExporter,
    SimpleExportSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

SPAN_PROCESSORS = {
    "batch": BatchExportSpanProcessor,
    "simple": SimpleExportSpanProcessor,
}

DEFAULT_SPAN_PROCESSOR_NAME = "batch"

LOGGER = logging.getLogger(__name__)


class LogSpanExporter(SpanExporter):
    def export(self, spans):
        for span in spans:
            LOGGER.debug(span)
        return SpanExportResult.SUCCESS


def _import_span_exporter(exporter_name):
    module_name, _, class_name = exporter_name.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _typify_config(config):
    typed_config = {}
    for key, value in config.items():
        try:
            value = ast.literal_eval(value)
        except ValueError:
            pass
        typed_config[key] = value
    return typed_config


def get_tracer(name):
    return trace.tracer_source().get_tracer(name)


def _set_in_dict(d, k, v):
    d[k] = v


def inject_trace_context(span, dictionary):
    TraceContextHTTPTextFormat().inject(span, _set_in_dict, dictionary)


def _get_from_dict(d, k):
    value = d.get(k)
    return [value] if value else []


def extract_trace_context(dictionary):
    return TraceContextHTTPTextFormat().extract(_get_from_dict, dictionary)


def event_id_from_span(span):
    context = span
    if isinstance(span, trace.Span):
        context = span.get_context()
    return format(context.trace_id, "x")


def configure_tracing(config, app_name, tracer_source=None):
    LOGGER.debug("Configuring tracing for %s", app_name)

    # In tests we don't want to set th preferred tracer source
    if tracer_source is None:
        trace.set_preferred_tracer_source_implementation(
            lambda T: TracerSource()
        )
        tracer_source = trace.tracer_source()

    for section_name in config.sections():
        match = re.match(r"tracing .+$", section_name, re.I)
        if not match:
            continue

        exporter_config = dict(config.items(section_name))
        try:
            exporter_name = exporter_config.pop("exporter")
        except KeyError:
            raise KeyError(
                "No 'exporter' configured for {}".format(section_name)
            )

        processor_name = exporter_config.pop(
            "span_processor", DEFAULT_SPAN_PROCESSOR_NAME
        )

        SpanProcessor = SPAN_PROCESSORS[processor_name]
        SpanExporter = _import_span_exporter(exporter_name)

        LOGGER.debug(
            "Adding span exporter %s using '%s' processor",
            exporter_name,
            processor_name,
        )

        exporter_config = _typify_config(exporter_config)
        # The console/log exporter doesn't support the service_name argument
        if not issubclass(
            SpanExporter, (ConsoleSpanExporter, LogSpanExporter)
        ):
            exporter_config["service_name"] = app_name

        span_exporter = SpanExporter(**exporter_config)
        tracer_source.add_span_processor(SpanProcessor(span_exporter))


class TracableMixin:
    @property
    def span(self):
        return getattr(self, "_span", None)

    @span.setter
    def span(self, span):
        self._span = span
        self._span.update_name(self.__class__.__name__)

    def start_span(self, tracer, **kwargs):
        self.span = tracer.start_span(**kwargs)

    def end_span(self):
        if self.span:
            self.span.end()
