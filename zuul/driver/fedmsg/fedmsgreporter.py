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
import voluptuous as v

from zuul.reporter import BaseReporter


class FedmsgReporter(BaseReporter):
    """Publish messages to a topic via fedmsg."""

    name = 'fedmsg'
    log = logging.getLogger("zuul.reporter.fedmsg.Reporter")

    def report(self, source, pipeline, item):
        """Publish messages to a topic via fedmsg."""
        message = self._formatItemReport(pipeline, item)

        self.log.debug("Report change %s, params %s, message: %s" %
                       (item.change, self.config, message))

        self.connection.publish(self.config['topic'], message)


def getSchema():
    fedmsg_reporter = v.Schema({
        'topic': str,
    })
    return fedmsg_reporter
