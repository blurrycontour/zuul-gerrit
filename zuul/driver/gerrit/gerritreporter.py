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

from zuul.driver.gerrit.gerritsource import GerritSource
from zuul.lib.logutil import get_annotated_logger
from zuul.reporter import BaseReporter


class GerritReporter(BaseReporter):
    """Sends off reports to Gerrit."""

    name = 'gerrit'
    log = logging.getLogger("zuul.GerritReporter")

    def _getFileComments(self, item):
        ret = {}
        for build in item.current_build_set.getBuilds():
            fc = build.result_data.get('zuul', {}).get('file_comments')
            if not fc:
                continue
            for fn, comments in fc.items():
                existing_comments = ret.setdefault(fn, [])
                existing_comments += comments
        self.addConfigurationErrorComments(item, ret)
        return ret

    def report(self, item):
        """Send a message to gerrit."""
        log = get_annotated_logger(self.log, item.event)

        # If the source is no GerritSource we cannot report anything here.
        if not isinstance(item.change.project.source, GerritSource):
            return

        # For supporting several Gerrit connections we also must filter by
        # the canonical hostname.
        if item.change.project.source.connection.canonical_hostname != \
                self.connection.canonical_hostname:
            return

        comments = self._getFileComments(item)
        self.filterComments(item, comments)
        message = self._formatItemReport(item)

        log.debug("Report change %s, params %s, message: %s, comments: %s",
                  item.change, self.config, message, comments)
        item.change._ref_sha = item.change.project.source.getRefSha(
            item.change.project, 'refs/heads/' + item.change.branch)

        # NOTE (felix): Is anything else from the config of interest for the later
        # gerrit action? Otherwise we can just evaluate the submit flag here.
        log.warning("config: %s" % self.config)
        action = {**self.config}
        log.warning("action before: %s" % action)
        direct_push = False
        if self.config.get("submit", False):
            direct_push = item.current_build_set.getDirectPush()
            if direct_push:
                log.debug("Submit and direct-push are enabled."
                          " Overwriting submit flag for gerrit review.")
                # We don't want the gerrit review to automatically submit the change,
                # thus we simply overwrite the submit flag for the gerrit review.
                action.pop("submit")
                #action["submit"] = False
        log.warning("action after: %s" % action)
        self.connection.review(item.change, message, action,
                               comments, zuul_event_id=item.event)

        # If the gerrit reporter is enabled to submit a change and direct-push
        # is activated for the active project, we directly push the change to
        # the remote
        if direct_push:
            log.debug("Direct-push is enabled. Going to push the change.")
            self.pushChange(item)

    def pushChange(self, item):
        log = get_annotated_logger(self.log, item.event)

        build_set = item.current_build_set

        self.connection.sched.merger.pushChanges(
            build_set.merger_items,  # TODO or [item] ?
            build_set
        )
        # TODO Wait for job to finish?

        # TODO How to determine if job was successful?
        item.change.is_merged = True
        return

    def getSubmitAllowNeeds(self):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return self.config


def getSchema():
    gerrit_reporter = v.Any(str, v.Schema(dict))
    return gerrit_reporter
