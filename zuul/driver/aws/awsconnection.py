# Copyright 2024 Acme Gating, LLC
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

import configparser
import logging
import os

from zuul.connection import BaseConnection


class AwsConnection(BaseConnection):
    driver_name = 'aws'
    log = logging.getLogger("zuul.AwsConnection")

    def __init__(self, driver, connection_name, connection_config):
        super().__init__(driver, connection_name, connection_config)

        # Users can provide credentials directly in zuul.conf, or via
        # standard AWS_ environment variables, or in the AWS shared
        # credentials file.  We will check those places in that order.
        self.shared_credentials_file = self.connection_config.get(
            'shared_credentials_file',
            os.getenv('AWS_SHARED_CREDENTIALS_FILE', None))

        self.access_key_id = self.connection_config.get(
            'access_key_id',
            os.getenv('AWS_ACCESS_KEY_ID', None))
        self.secret_access_key = self.connection_config.get(
            'secret_access_key',
            os.getenv('AWS_SECRET_ACCESS_KEY', None))
        self.profile = self.connection_config.get(
            'profile',
            os.getenv('AWS_PROFILE', 'default'))

        if (not self.access_key_id) and self.shared_credentials_file:
            path = os.path.expanduser(self.shared_credentials_file)
            config = configparser.ConfigParser()
            config.read(path)

            section = config[self.profile]
            self.access_key_id = section['access_key_id']
            self.secret_access_key = section['secret_access_key']

        if not self.access_key_id and not self.secret_access_key:
            raise Exception("AWS credentials not found")
