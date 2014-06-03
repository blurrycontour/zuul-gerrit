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

    name = 'gerrit'
    log = logging.getLogger("zuul.reporter.gerrit.Reporter")

    def __init__(self, trigger):
        """Set up the reporter."""
        self.default_gerrit = trigger.gerrit
        self.trigger = trigger

    def report(self, change, message, params):
        """Send a message to gerrit."""
        self.log.debug("Report change %s, params %s, message: %s" %
                       (change, params, message))
        changeid = '%s,%s' % (change.number, change.patchset)
        change._ref_sha = self.trigger.getRefSha(change.project.name,
                                                 'refs/heads/' + change.branch)

        if any(x in params for x in ['gerrit_server', 'gerrit_user',
                                     'gerrit_port', 'gerrit_keyfile']):
            # This reporter is configured to report as a different user back
            # into gerrit. Create a new session.
            # We'll inherit the default connection parameters (such as host and
            # sshkey) if they aren't set explicitly for this user.
            report_gerrit = gerrit.Gerrit(
                params.get('gerrit_server', self.default_gerrit.hostname),
                params.get('gerrit_user', self.default_gerrit.username),
                params.get('gerrit_port', self.default_gerrit.port),
                params.get('gerrit_keyfile', self.default_gerrit.keyfile)
            )
        else:
            report_gerrit = self.default_gerrit

        return report_gerrit.review(change.project.name, changeid, message,
                                    params)

    def getSubmitAllowNeeds(self, params):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return params
