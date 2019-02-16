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

from zuul.driver import ConnectionInterface, Driver, TriggerInterface
from zuul.driver.amqp import amqpconnection
from zuul.driver.amqp import amqptrigger


class AMQPDriver(Driver, ConnectionInterface, TriggerInterface):
    name = 'amqp'

    def __init__(self):
        self.tenants = {}

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def reconfigure(self, tenant):
        self.tenants[tenant.name] = []
        for pipeline in tenant.layout.pipelines.values():
            for ef in pipeline.manager.event_filters:
                if isinstance(ef.trigger, amqptrigger.AMQPTrigger):
                    self.tenants[tenant.name].append(pipeline.name)

    def getConnection(self, name, config):
        return amqpconnection.AMQPConnection(self, name, config)

    def getTrigger(self, connection, config=None):
        return amqptrigger.AMQPTrigger(self, connection, config)

    def getTriggerSchema(self):
        return amqptrigger.getSchema()
