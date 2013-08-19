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
import smtplib

from email.mime.text import MIMEText


class Reporter(object):
    name = 'SMTP Reporter'
    log = logging.getLogger("zuul.reporter.smtp.Reporter")

    def __init__(self, config, trigger):
        self.config = config
        self.trigger = trigger

    def report(self, change, message, action):
        self.log.debug("Report change %s, action %s, message: %s" %
                       (change, action, message))
        if not change.number:
            self.log.debug("Change has no number; not reporting")
            return
        if not action:
            self.log.debug("No action specified; not reporting")
            return

        # Create a text/plain email message
        from_email = action['from']\
            if 'from' in action else self.config.get('smtp', 'default_from')
        to_email = action['to']\
            if 'to' in action else self.config.get('smtp', 'default_to')
        msg = MIMEText(message)
        msg['Subject'] = "Report change %s" % change
        msg['From'] = from_email
        msg['To'] = to_email

        s = smtplib.SMTP(self.config.get('smtp', 'server'))
        s.sendmail(from_email, to_email.split(','), msg.as_string())
        s.quit()
