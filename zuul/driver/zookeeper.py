# Copyright 2018 Red Hat
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

from aiohttp import web

import zuul.zk

from zuul.lib.config import get_default
from zuul.driver import Driver, ConnectionInterface
from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebHandler, StaticHandler


class ZookeeperDriver(Driver, ConnectionInterface):
    name = 'zookeeper'

    def getConnection(self, name, config):
        return ZookeeperConnection(self, name, config)


class ZookeeperConnection(BaseConnection):
    driver_name = 'zookeeper'
    log = logging.getLogger("zuul.ZookeeperConnection")

    def __init__(self, driver, driver_name, config):
        super().__init__(driver, driver_name, {})
        self.zk_args = {
            'hosts': get_default(config, 'zookeeper',
                                 'hosts', '127.0.0.1:2181'),
            'read_only': True,
        }

    def validateWebConfig(self, config, connections):
        return True

    def getWebHandlers(self, zuul_web, info):
        self.zk = zuul.zk.ZooKeeper()
        self.zk.connect(**self.zk_args)
        return [
            ZookeeperWebHandler(self, zuul_web, 'GET', '/{tenant}/labels'),
            ZookeeperWebHandler(self, zuul_web, 'GET', '/{tenant}/nodes'),
            StaticHandler(zuul_web, '/{tenant}/labels.html'),
        ]


class ZookeeperWebHandler(BaseWebHandler):
    log = logging.getLogger("zuul.ZookeeperWebHandler")

    def getLabels(self, tenant):
        labels = set()
        for launcher in self.connection.zk.getRegisteredLaunchers():
            for label in launcher.supported_labels:
                labels.add(label)
        return [{'name': label} for label in sorted(labels)]

    def getNodes(self, tenant):
        nodes = []
        for node in self.connection.zk.nodeIterator():
            node_data = {}
            for key in ("type", "connection_type", "public_ipv4",
                        "connection_port", "provider", "state"):
                node_data[key] = node.get(key)
            nodes.append(node_data)
        return nodes

    async def handleRequest(self, request):
        try:
            tenant = request.match_info["tenant"]
            if request.url.path.split('/')[-1] == "nodes":
                data = self.getNodes(tenant)
            else:
                data = self.getLabels(tenant)
            resp = web.json_response(data)
            resp.headers['Access-Control-Allow-Origin'] = '*'
        except Exception as e:
            self.log.exception("ZookeeperHandler exception:")
            resp = web.json_response({'error_description': 'Internal error'},
                                     status=500)
        return resp
