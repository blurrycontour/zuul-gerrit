# Copyright 2013 Rackspace Australia
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

from zuul.reporter import BaseReporter, safe_template_value


class SMTPReporter(BaseReporter):
    """Sends off reports to emails via SMTP."""

    name = 'smtp'
    log = logging.getLogger("zuul.SMTPReporter")

    def report(self, item):
        """Send the compiled report message via smtp."""
        message = self._formatItemReport(item)

        self.log.debug("Report change %s, params %s, message: %s" %
                       (item.change, self.config, message))

        from_email = self.config['from'] \
            if 'from' in self.config else None
        to_email = self.config['to'] \
            if 'to' in self.config else None

        if 'subject' in self.config:
            subject = self.safeFormatTemplate(self.config['subject'], item)
        else:
            subject = "Report for change %s" % item.change

        if subject is not None:
            self.connection.sendMail(subject, message, from_email, to_email)


def getSchema():
    smtp_reporter = v.Schema({
        'to': str,
        'from': str,
        'subject': safe_template_value,
    })
    return smtp_reporter
