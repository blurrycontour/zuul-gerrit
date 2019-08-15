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

    def __init__(self, driver, connection, config=None):
        super(GerritReporter, self).__init__(driver, connection, config)
        action = self.config.copy()
        self._create_comment = action.pop('comment', True)
        self._submit = action.pop('submit', False)
        self._checks_api = action.pop('checks-api', None)
        self._labels = action

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
        if self._create_comment:
            message = self._formatItemReport(item)
        else:
            message = ''

        log.debug("Report change %s, params %s, message: %s, comments: %s",
                  item.change, self.config, message, comments)
        item.change._ref_sha = item.change.project.source.getRefSha(
            item.change.project, 'refs/heads/' + item.change.branch)

        direct_push = False
        # If the gerrit reporter is enabled for submitting the change, we
        # evaluate the direct-push flag from the config.
        if self._submit:
            direct_push = item.current_build_set.getDirectPush()
            if direct_push:
                log.debug("Direct-push is enabled. Going to push the change.")
                # As we are going to push the change directly, there is no need
                success, error = self.pushChange(item)
                if not success:
                    # Report failure reason to gerrit review
                    message = "{} But could not be pushed directly: {}".format(
                        message, error)
                    # TODO Test if the _submit=True has any drawback if the change
                    # is already pushed.

                    # If the direct-push failes, prevent gerrit from submitting
                    # the change. Dependening on the merge algorithm used, this
                    # might still be possible, but could lead to a different
                    # result.
                    self._submit = False

        self.log.debug("Gerrit message: %s", message)
        self.connection.review(item, message, self._submit,
                               self._labels, self._checks_api,
                               comments, zuul_event_id=item.event)

    def pushChange(self, item):
        log = get_annotated_logger(self.log, item.event)
        build_set = item.current_build_set
        log.debug("Pushing items %s for buildset %s",
                  build_set.merger_items, build_set)

        job = self.connection.sched.merger.pushChanges(
            build_set.merger_items,  # TODO or [item] ?
            build_set
        )
        self.log.debug("Waiting for pushChanges job %s" % job)
        job.wait()

        if not job.updated:
            return False, "PushChanges job {} failed".format(job)

        #item.change.is_merged = True
        #item.change["status"] = "MERGED"
        return True, None

    def getSubmitAllowNeeds(self):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return self._labels


def getSchema():
    gerrit_reporter = v.Any(str, v.Schema(dict))
    return gerrit_reporter
