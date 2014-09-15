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

from zuul.reporter import BaseReporter


class SMTPReporter(BaseReporter):
    """Sends off reports to emails via SMTP."""

    name = 'smtp'
    log = logging.getLogger("zuul.reporter.smtp.Reporter")

    def report(self, source, change, message, params):
        """Send the compiled report message via smtp."""
        self.log.debug("Report change %s, params %s, message: %s" %
                       (change, params, message))

        from_email = params['from'] if 'from' in params else None
        to_email = params['to'] if 'to' in params else None

        if 'subject' in params:
            subject = params['subject'].format(change=change)
        else:
            subject = "Report for change %s" % change

        self.connection._send_mail(subject, message, from_email, to_email)
