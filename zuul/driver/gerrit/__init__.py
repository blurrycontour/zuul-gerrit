# Copyright 2016 Red Hat, Inc.
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

import gerritconnection as connection
import gerrittrigger as trigger
import gerritsource as source
import gerritreporter as reporter

class GerritDriver(object):
    name = 'gerrit'

    def getConnection(self, name, config):
        return connection.GerritConnection(self, name, config)

    def getTrigger(self, connection):
        return trigger.GerritTrigger(self)

    def getSource(self, connection):
        return source.GerritSource(self, connection)

    def getReporter(self, connection):
        return reporter.GerritReporter(self, connection)
