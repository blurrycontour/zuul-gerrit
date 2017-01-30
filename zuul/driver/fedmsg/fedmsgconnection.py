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

import fedmsg
import logging
import voluptuous as v

from zuul.connection import BaseConnection


class FedmsgConnection(BaseConnection):
    driver_name = 'fedmsg'
    log = logging.getLogger("connection.fedmsg")

    def __init__(self, driver, connection_name, connection_config):
        super(FedmsgConnection, self).__init__(driver, connection_name,
                                               connection_config)

    def publish(self, topic, message):
        try:
            fedmsg.publish(topic=topic, msg=message)
        except:
            self.log.exception(
                "Could not publish message to topic '%s' via fedmsg", topic)
        return


def getSchema():
    fedmsg_connection = v.Any(str, v.Schema({}, extra=True))
    return fedmsg_connection
