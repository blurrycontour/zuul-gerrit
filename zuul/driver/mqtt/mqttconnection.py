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

    def configure_tls(self):
        ca_certs = self.connection_config.get('ca_certs')
        certfile = self.connection_config.get('certfile')
        keyfile = self.connection_config.get('keyfile')
        ciphers = self.connection_config.get('ciphers')
        tls_version = self.connection_config.get('tls_version')
        if (certfile or keyfile or ciphers or tls_version) and not ca_certs:
            raise ConfigurationError(
                "MQTT TLS configuration requires the ca_certs option")
        if ca_certs:
            if (certfile and not keyfile) or (not certfile and keyfile):
                raise ConfigurationError(
                    "MQTT configuration keyfile and certfile "
                    "options must both be set.")
            if tls_version:
                try:
                    tls_version = getattr(ssl, 'PROTOCOL_%s' % tls_version)
                except AttributeError:
                    tls_versions = list(filter(
                        lambda x: x.startswith('PROTOCOL_TLSv'), dir(ssl)))
                    raise ConfigurationError(
                        "%s: Unknown tls_version (supported: %s)" % (
                            tls_version, tls_versions))
            self.client.tls_set(
                ca_certs=ca_certs,
                certfile=certfile,
                keyfile=keyfile,
                tls_version=tls_version,
                ciphers=ciphers)

    def __init__(self, driver, connection_name, connection_config):
        super(MQTTConnection, self).__init__(
            driver, connection_name, connection_config)
        self.client = mqtt.Client(
            client_id=self.connection_config.get('client_id'))
        if self.connection_config.get('user'):
            self.client.username_pw_set(
                self.connection_config.get('user'),
                self.connection_config.get('password'))
        self.configure_tls()
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
