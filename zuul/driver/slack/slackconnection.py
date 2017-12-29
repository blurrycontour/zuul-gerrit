# Copyright 2014 Rackspace Australia
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

import voluptuous as v
import slackclient

from zuul.connection import BaseConnection


class SlackConnection(BaseConnection):
    driver_name = 'slack'
    log = logging.getLogger("zuul.SlackConnection")

    def __init__(self, driver, connection_name, connection_config):

        super(SlackConnection, self).__init__(driver, connection_name,
                                              connection_config)

        self.token = self.connection_config.get('token')
        self.client = slackclient.SlackClient(self.token)
        self.subject = self.connection_config.get(
            'subject', 'Report for {change} in {change.project}')


def getSchema():
    slack_connection = v.Any(str, v.Schema(dict))
    return slack_connection
