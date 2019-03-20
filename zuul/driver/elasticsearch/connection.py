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

import time
import logging

from elasticsearch import Elasticsearch
from elasticsearch.client import IndicesClient
from elasticsearch.helpers import bulk
from elasticsearch.helpers import BulkIndexError

from zuul.connection import BaseConnection

EL_RESERVED_FIELDS = [
    '_index',
    '_uid',
    '_type',
    '_id',
    '_source',
    '_size',
    '_all',
    '_field_names',
    '_timestamp',
    '_ttl',
    '_parent',
    '_routing',
    '_meta',
]


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

    dynamic_template = [
        {
            "strings": {
                "match": "job_param.*",
                "mapping": {
                    "type": "keyword",
                }
            }
        }
    ]

    def __init__(self, driver, connection_name, connection_config):
        super(ElasticsearchConnection, self).__init__(
            driver, connection_name, connection_config)
        self.uri = self.connection_config.get('uri')
        self.index = self.connection_config.get('index')
        self.es = Elasticsearch(self.uri)
        self.ic = IndicesClient(self.es)
        self.setIndex()
        self.setMapping()

    def setIndex(self):
        self.ic.create(index=self.index, ignore=400)
        while not self.ic.exists(index=self.index):
            time.sleep(0.2)

    def setMapping(self):
        mapping = {
            'zuul': {
                "properties": self.properties,
                "dynamic_templates": self.dynamic_template,
            }
        }
        if not self.ic.exists_type(
            index=self.index, doc_type="zuul"):
            self.ic.put_mapping(
                index=self.index, doc_type="zuul", body=mapping)

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
