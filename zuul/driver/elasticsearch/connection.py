# Copyright 2019 Red Hat, Inc.
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

import types
import logging

from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.helpers import bulk
from elasticsearch.helpers import BulkIndexError
from elasticsearch.serializer import JSONSerializer

from zuul.connection import BaseConnection


class Encoder(JSONSerializer):
    def default(self, obj):
        if isinstance(obj, types.MappingProxyType):
            return dict(obj)
        return JSONSerializer.default(self, obj)


class ElasticsearchConnection(BaseConnection):
    driver_name = 'elasticsearch'
    log = logging.getLogger("zuul.ElasticSearchConnection")
    properties = {
        #  Common attribute
        "uuid": {"type": "keyword"},
        "build_type": {"type": "keyword"},
        "result": {"type": "keyword"},
        "duration": {"type": "integer"},
        # BuildSet type specific attributes
        "zuul_ref": {"type": "keyword"},
        "pipeline": {"type": "keyword"},
        "project": {"type": "keyword"},
        "branch": {"type": "keyword"},
        "change": {"type": "integer"},
        "patchset": {"type": "keyword"},
        "ref": {"type": "keyword"},
        "oldrev": {"type": "keyword"},
        "newrev": {"type": "keyword"},
        "ref_url": {"type": "keyword"},
        "message": {"type": "text"},
        "tenant": {"type": "keyword"},
        # Build type specific attibutes
        "buildset_uuid": {"type": "keyword"},
        "job_name": {"type": "keyword"},
        "start_time": {"type": "date", "format": "epoch_second"},
        "end_time": {"type": "date", "format": "epoch_second"},
        "voting": {"type": "boolean"},
        "log_url": {"type": "keyword"},
        "node_name": {"type": "keyword"}
    }

    def __init__(self, driver, connection_name, connection_config):
        super(ElasticsearchConnection, self).__init__(
            driver, connection_name, connection_config)
        self.uri = self.connection_config.get('uri').split(',')
        self.cnx_opts = {}
        use_ssl = self.connection_config.get('use_ssl', False)
        if use_ssl:
            if use_ssl.lower() == 'true':
                use_ssl = True
            else:
                use_ssl = False
        verify_certs = self.connection_config.get('verify_certs', False)
        if verify_certs:
            if verify_certs.lower() == 'true':
                verify_certs = True
            else:
                verify_certs = False
        self.cnx_opts['ca_certs'] = self.connection_config.get(
            'ca_certs', None)
        self.cnx_opts['client_cert'] = self.connection_config.get(
            'client_cert', None)
        self.cnx_opts['client_key'] = self.connection_config.get(
            'client_key', None)
        self.index = self.connection_config.get('index')
        self.es = Elasticsearch(
            self.uri, serializer=Encoder(), **self.cnx_opts)
        self.ic = IndicesClient(self.es)
        self.setIndex()

    def setIndex(self):
        settings = {
            'mappings': {
                'zuul': {
                    "properties": self.properties
                }
            }
        }
        try:
            self.ic.create(index=self.index, ignore=400, body=settings)
        except Exception:
            self.log.exception(
                "Unable to create the index %s on connection %s" % (
                    self.index, self.connection_name))

    def add_docs(self, source_it):
        def gen(it):
            for source in it:
                d = {}
                d['_index'] = self.index
                d['_type'] = 'zuul'
                d['_op_type'] = 'index'
                d['_source'] = source
                yield d
        try:
            bulk(self.es, gen(source_it))
            self.log.info('%s docs indexed to %s' % (
                len(source_it), self.connection_name))
        except BulkIndexError as exc:
            self.log.warn("Some docs failed to be indexed (%s)" % exc)
        self.es.indices.refresh(index=self.index)
