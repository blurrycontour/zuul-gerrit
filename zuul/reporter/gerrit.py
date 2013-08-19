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

from zuul.lib import gerrit


class Reporter(object):
    """Sends off reports to Gerrit."""

    name = 'Gerrit Reporter'
    log = logging.getLogger("zuul.reporter.gerrit.Reporter")

    def __init__(self, config, trigger=None):
        """Set up the reporter.

        Takes a ConfigParser object and optionally the trigger which
        initiated the job.

        """
        self.config = config
        self.trigger = trigger
        self._get_gerrit()

    def _get_gerrit(self):
        """Get a zuul.lib.gerrit.Gerrit instance.

        Grabs from either the trigger if it has already instantiated
        one or start one now.

        """

        if self.trigger and self.trigger.name == 'gerrit':
            self.gerrit = self.trigger.gerrit
        elif self.config:
            self.gerrit = gerrit.Gerrit(self.config)

    def report(self, change, message, action):
        """Send a message to gerrit."""

        self.log.debug("Report change %s, action %s, message: %s" %
                       (change, action, message))

        if not action:
            self.log.debug("Not reporting change %s: No action specified." %
                           change)
            return

        changeid = '%s,%s' % (change.number, change.patchset)
        ref = 'refs/heads/' + change.branch
        change._ref_sha = self.trigger.getRefSha(change.project.name, ref)
        return self.gerrit.review(change.project.name, changeid, message,
                                  action)
