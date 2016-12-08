# Copyright 2015 Rackspace Australia
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

import re

import zuul.driver.zuul
import zuul.driver.gerrit
import zuul.driver.smtp

class ConnectionRegistry(object):
    """A registry of connections"""

    def __init__(self):
        self.connections = {}
        self.drivers = {}

        self.registerDriver(zuul.driver.zuul.ZuulDriver())
        self.registerDriver(zuul.driver.gerrit.GerritDriver())
        self.registerDriver(zuul.driver.smtp.SMTPDriver())

    def registerDriver(self, driver):
        if driver.name in self.drivers:
            raise Exception("Driver %s already registered" % driver.name)
        self.drivers[driver.name] = driver

    def registerScheduler(self, sched, load=True):
        for connection_name, connection in self.connections.items():
            connection.registerScheduler(sched)
            if load:
                connection.onLoad()

    def stop(self):
        for connection_name, connection in self.connections.items():
            connection.onStop()

    def configure(self, config):
        print 'configure'
        # Register connections from the config
        # TODO(jhesketh): import connection modules dynamically
        connections = {}

        for section_name in config.sections():
            con_match = re.match(r'^connection ([\'\"]?)(.*)(\1)$',
                                 section_name, re.I)
            if not con_match:
                continue
            con_name = con_match.group(2)
            con_config = dict(config.items(section_name))

            if 'driver' not in con_config:
                raise Exception("No driver specified for connection %s."
                                % con_name)

            con_driver = con_config['driver']
            if con_driver not in self.drivers:
                raise Exception("Unknown driver, %s, for connection %s"
                                % (con_config['driver'], con_name))

            driver = self.drivers[con_driver]
            print 'driver', driver
            connection = driver.getConnection(con_name, con_config)
            print 'connection', connection
            connections[con_name] = connection

        # If the [gerrit] or [smtp] sections still exist, load them in as a
        # connection named 'gerrit' or 'smtp' respectfully

        if 'gerrit' in config.sections():
            driver = self.drivers['gerrit']
            connections['gerrit'] = \
                driver.getConnection(
                    'gerrit', dict(config.items('gerrit')))

        if 'smtp' in config.sections():
            driver = self.drivers['smtp']
            connections['smtp'] = \
                driver.getConnection(
                    'smtp', dict(config.items('smtp')))

        self.connections = connections

    def _getDriver(self, connection_name):
        if connection_name in self.connections:
            connection = self.connections[connection_name]
            driver = self.connections[connection_name].driver
        else:
            # In some cases a driver may not be related to a connection. For
            # example, the 'timer' or 'zuul' triggers.
            connection = None
            driver = self.drivers[connection_name]

        return connection, driver

    def getSource(self, connection_name):
        connection, driver = self._getDriver(connection_name)
        return driver.getSource(connection)

    def getReporter(self, connection_name, driver_config={}):
        connection, driver = self._getDriver(connection_name)
        return driver.getReporter(connection)

    def getTrigger(self, connection_name, driver_config={}):
        connection, driver = self._getDriver(connection_name)
        return driver.getTrigger(connection)
