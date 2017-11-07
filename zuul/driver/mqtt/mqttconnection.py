# Copyright 2017 Red Hat, Inc.
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
import json

import voluptuous as v
import paho.mqtt.client as mqtt

from zuul.connection import BaseConnection


class MQTTConnection(BaseConnection):
    driver_name = 'mqtt'
    log = logging.getLogger("zuul.MQTTConnection")

    def __init__(self, driver, connection_name, connection_config):
        super(MQTTConnection, self).__init__(driver, connection_name,
                                             connection_config)
        if 'server' not in self.connection_config:
            raise Exception('server is required for mqtt connections in '
                            '%s' % self.connection_name)
        if 'user' not in self.connection_config:
            raise Exception('user is required for mqtt connections in '
                            '%s' % self.connection_name)
        self.user = self.connection_config.get('user')
        self.password = self.connection_config.get('password')
        self.client = mqtt.Client(client_id=self.connection_config.get(
            'client_id'))
        self.client.username_pw_set(
            self.connection_config.get('user'),
            self.connection_config.get('password'))
        self.connected = False
        try:
            self.client.connect(
                self.connection_config.get('server'),
                port=int(self.connection_config.get('port', 1883))
            )
            self.connected = True
        except Exception:
            self.log.exception("MQTT reporter (%s) couldn't connect" % self)

    def publish(self, topic, message):
        if not self.connected:
            self.log.warn("MQTT reporter (%s) is disabled" % self)
            return
        try:
            self.client.publish(topic, payload=json.dumps(message))
        except Exception:
            self.log.exception(
                "Could not publish message to topic '%s' via mqtt", topic)


def getSchema():
    return v.Any(str, v.Schema(dict))
