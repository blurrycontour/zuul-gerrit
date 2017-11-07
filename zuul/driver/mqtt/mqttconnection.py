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
import ssl

import voluptuous as v
import paho.mqtt.client as mqtt

from zuul.connection import BaseConnection
from zuul.exceptions import ConfigurationError


class MQTTConnection(BaseConnection):
    driver_name = 'mqtt'
    log = logging.getLogger("zuul.MQTTConnection")

    def _translate_tls_version(self, tls_version):
        """Convert tls version string from config to ssl id"""
        tls_versions = {
            'tlsv1': ssl.PROTOCOL_TLSv1,
            'tlsv1.1': ssl.PROTOCOL_TLSv1_1,
            'tlsv1.2': ssl.PROTOCOL_TLSv1_2,
        }
        try:
            return tls_versions[tls_version.lower()]
        except KeyError:
            msg = "%s: unknown tls version (supported: %s)" % (
                tls_version, list(tls_versions.keys()))
            self.log.error(msg)
            raise ConfigurationError(msg)

    def __init__(self, driver, connection_name, connection_config):
        super(MQTTConnection, self).__init__(driver, connection_name,
                                             connection_config)
        self.client = mqtt.Client(
            client_id=self.connection_config.get('client_id'))
        if self.connection_config.get('user'):
            self.client.username_pw_set(
                self.connection_config.get('user'),
                self.connection_config.get('password'))
        ca_certs = self.connection_config.get('ca_certs')
        certfile = self.connection_config.get('certfile')
        keyfile = self.connection_config.get('keyfile')
        if (certfile or keyfile) and not ca_certs:
            raise Exception("MQTT TLS configuration requires "
                            "the ca_certs option")
        if ca_certs:
            if (certfile and not keyfile) or (not certfile and keyfile):
                raise Exception("MQTT configuration keyfile and certfile "
                                "options must both be set.")
            self.client.tls_set(
                ca_certs,
                certfile=certfile,
                keyfile=keyfile,
                tls_version=self._get_tls_version(
                    self.connection_config.get('tls_version', 'tlsv1')),
                ciphers=self.connection_config.get('ciphers'))
        self.connected = False

    def onLoad(self):
        self.log.debug("Starting MQTT Connection")
        try:
            self.client.connect(
                self.connection_config.get('server', 'localhost'),
                port=int(self.connection_config.get('port', 1883)),
                keepalive=int(self.connection_config.get('keepalive', 60))
            )
            self.connected = True
        except Exception:
            self.log.exception("MQTT reporter (%s) couldn't connect" % self)
        self.client.loop_start()

    def onStop(self):
        self.log.debug("Stopping MQTT Connection")
        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False

    def publish(self, topic, message, qos):
        if not self.connected:
            self.log.warn("MQTT reporter (%s) is disabled" % self)
            return
        try:
            self.client.publish(topic, payload=json.dumps(message), qos=qos)
        except Exception:
            self.log.exception(
                "Could not publish message to topic '%s' via mqtt", topic)


def getSchema():
    return v.Any(str, v.Schema(dict))
