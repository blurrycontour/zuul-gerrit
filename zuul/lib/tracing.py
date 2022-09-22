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
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from zuul.lib.config import get_default, any_to_bool


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

    def test(self):
        # TODO: remove once we have actual traces
        if not self.tracer:
            return
        with self.tracer.start_as_current_span('test-trace'):
            pass
