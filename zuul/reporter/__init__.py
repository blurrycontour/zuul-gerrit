# Copyright 2014 Rackspace Australia
# Copyright 2021-2024 Acme Gating, LLC
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

import abc
import logging
from zuul.lib.config import get_default


class BaseReporter(object, metaclass=abc.ABCMeta):
    """Base class for reporters.

    Defines the exact public methods that must be supplied.
    """

    log = logging.getLogger("zuul.reporter.BaseReporter")

    def __init__(self, driver, connection, config=None):
        self.driver = driver
        self.connection = connection
        self.config = config or {}
        self._action = None

    def setAction(self, action):
        self._action = action

    @abc.abstractmethod
    def report(self, item, phase1=True, phase2=True):
        """Send the compiled report message

        Two-phase reporting may be enabled if one or the other of the
        `phase1` or `phase2` arguments is False.

        Phase1 should report everything except the actual merge action.
        Phase2 should report only the merge action.

        :arg phase1 bool: Whether to enable phase1 reporting
        :arg phase2 bool: Whether to enable phase2 reporting

        """

    def getSubmitAllowNeeds(self):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return []

    def postConfig(self):
        """Run tasks after configuration is reloaded"""

    def addConfigurationErrorComments(self, item, change, comments):
        """Add file comments for configuration errors.

        Updates the comments dictionary with additional file comments
        for any relevant configuration errors for the specified change.

        :arg QueueItem item: The queue item
        :arg Ref change: One of the item's changes to check
        :arg dict comments: a file comments dictionary

        """

        for err in item.getConfigErrors():
            context = err.key.context
            mark = err.key.mark
            if not (context and mark and err.short_error):
                continue
            if context.project_canonical_name != \
                    change.project.canonical_name:
                continue
            if not hasattr(change, 'branch'):
                continue
            if context.branch != change.branch:
                continue
            if context.path not in change.files:
                continue
            existing_comments = comments.setdefault(context.path, [])
            existing_comments.append(dict(line=mark.end_line,
                                          message=err.short_error,
                                          range=dict(
                                              start_line=mark.line + 1,
                                              start_character=mark.column,
                                              end_line=mark.end_line,
                                              end_character=mark.end_column)))

    def _getFileComments(self, item, change):
        """Get the file comments from the zuul_return value"""
        ret = {}
        for build in item.current_build_set.getBuilds():
            fc = build.result_data.get("zuul", {}).get("file_comments")
            if not fc:
                continue
            # Only consider comments for this change
            if change.cache_key not in build.job.all_refs:
                continue
            for fn, comments in fc.items():
                existing_comments = ret.setdefault(fn, [])
                existing_comments.extend(comments)
        self.addConfigurationErrorComments(item, change, ret)
        return ret

    def getFileComments(self, item, change):
        comments = self._getFileComments(item, change)
        self.filterComments(item, change, comments)
        return comments

    def filterComments(self, item, change, comments):
        """Filter comments for files in change

        Remove any comments for files which do not appear in the
        specified change.  Leave warning messages if this happens.

        :arg QueueItem item: The queue item
        :arg Change change: The change
        :arg dict comments: a file comments dictionary (modified in place)
        """

        for fn in list(comments.keys()):
            if fn not in change.files:
                del comments[fn]
                item.warning("Comments left for invalid file %s" % (fn,))

    def _getFormatter(self, action):
        format_methods = {
            'enqueue': self._formatItemReportEnqueue,
            'start': self._formatItemReportStart,
            'success': self._formatItemReportSuccess,
            'failure': self._formatItemReportFailure,
            'merge-conflict': self._formatItemReportMergeConflict,
            'merge-failure': self._formatItemReportMergeFailure,
            'config-error': self._formatItemReportConfigError,
            'no-jobs': self._formatItemReportNoJobs,
            'disabled': self._formatItemReportDisabled,
            'dequeue': self._formatItemReportDequeue,
        }
        return format_methods[action]

    def _formatItemReport(self, item, with_jobs=True, action=None):
        """Format a report from the given items. Usually to provide results to
        a reporter taking free-form text."""
        action = action or self._action
        ret = self._getFormatter(action)(item, with_jobs)

        config_warnings = item.getConfigErrors(errors=False, warnings=True)
        if config_warnings:
            ret += '\nWarning:\n  ' + config_warnings[0].error + '\n'

        if item.current_build_set.warning_messages:
            warning = '\n  '.join(item.current_build_set.warning_messages)
            ret += '\nWarning:\n  ' + warning + '\n'

        if item.current_build_set.debug_messages:
            debug = '\n  '.join(item.current_build_set.debug_messages)
            ret += '\nDebug information:\n  ' + debug + '\n'

        if item.pipeline.footer_message:
            ret += '\n' + item.pipeline.footer_message

        return ret

    def _formatItemReportEnqueue(self, item, with_jobs=True):
        status_url = self.connection.sched.globals.web_status_url
        if status_url:
            status_url = item.formatUrlPattern(status_url)

        # change, changes, and status_url are deprecated
        return item.pipeline.enqueue_message.format(
            pipeline=item.pipeline.getSafeAttributes(),
            change=item.changes[0].getSafeAttributes(),
            changes=[c.getSafeAttributes() for c in item.changes],
            item_url=item.formatItemUrl(),
            status_url=status_url)

    def _formatItemReportStart(self, item, with_jobs=True):
        status_url = self.connection.sched.globals.web_status_url
        if status_url:
            status_url = item.formatUrlPattern(status_url)

        # change, changes, and status_url are deprecated
        return item.pipeline.start_message.format(
            pipeline=item.pipeline.getSafeAttributes(),
            change=item.changes[0].getSafeAttributes(),
            changes=[c.getSafeAttributes() for c in item.changes],
            item_url=item.formatItemUrl(),
            status_url=status_url)

    def _formatItemReportSuccess(self, item, with_jobs=True):
        msg = item.pipeline.success_message
        if with_jobs:
            item_url = item.formatItemUrl()
            if item_url is not None:
                msg += '\n' + item_url
            msg += '\n\n' + self._formatItemReportJobs(item)
        return msg

    def _formatItemReportFailure(self, item, with_jobs=True):
        if len(item.changes) > 1:
            change_text = 'These changes'
        else:
            change_text = 'This change'
        if item.dequeued_needing_change:
            msg = f'{change_text} depends on a change that failed to merge.\n'
            if isinstance(item.dequeued_needing_change, str):
                msg += '\n' + item.dequeued_needing_change + '\n'
        elif item.dequeued_missing_requirements:
            msg = (f'{change_text} is unable to merge '
                   'due to a missing merge requirement.\n')
        elif len(item.changes) > 1:
            msg = f'{change_text} is part of a dependency cycle that failed.\n'
            if with_jobs:
                msg = '{}\n\n{}'.format(msg, self._formatItemReportJobs(item))
            msg = "{}\n\n{}".format(
                msg, self._formatItemReportOtherChanges(item))
        elif item.didMergerFail():
            msg = item.pipeline.merge_conflict_message
        elif item.current_build_set.has_blocking_errors:
            msg = str(item.getConfigErrors(
                errors=True, warnings=False)[0].error)
        else:
            msg = item.pipeline.failure_message
            if with_jobs:
                item_url = item.formatItemUrl()
                if item_url is not None:
                    msg += '\n' + item_url
                msg += '\n\n' + self._formatItemReportJobs(item)
        return msg

    def _formatItemReportMergeConflict(self, item, with_jobs=True):
        return item.pipeline.merge_conflict_message

    def _formatItemReportMergeFailure(self, item, with_jobs=True):
        return 'This change was not merged by the code review system.\n'

    def _formatItemReportConfigError(self, item, with_jobs=True):
        if item.getConfigErrors():
            msg = str(item.getConfigErrors()[0].error)
        else:
            msg = "Unknown configuration error"
        return msg

    def _formatItemReportNoJobs(self, item, with_jobs=True):
        status_url = get_default(self.connection.sched.config,
                                 'web', 'status_url', '')
        if status_url:
            status_url = item.formatUrlPattern(status_url)

        # change, changes, and status_url are deprecated
        return item.pipeline.no_jobs_message.format(
            pipeline=item.pipeline.getSafeAttributes(),
            change=item.changes[0].getSafeAttributes(),
            changes=[c.getSafeAttributes() for c in item.changes],
            item_url=item.formatItemUrl(),
            status_url=status_url)

    def _formatItemReportDisabled(self, item, with_jobs=True):
        if item.current_build_set.result == 'SUCCESS':
            return self._formatItemReportSuccess(item)
        elif item.current_build_set.result == 'FAILURE':
            return self._formatItemReportFailure(item)
        else:
            return self._formatItemReport(item)

    def _formatItemReportDequeue(self, item, with_jobs=True):
        msg = item.pipeline.dequeue_message
        if with_jobs:
            msg += '\n\n' + self._formatItemReportJobs(item)
        return msg

    def _formatItemReportOtherChanges(self, item):
        return "Related changes:\n{}\n".format("\n".join(
            f'  - {c.url}' for c in item.changes))

    def _getItemReportJobsFields(self, item):
        # Extract the report elements from an item
        config = self.connection.sched.config
        jobs_fields = []
        skipped = 0
        for job in item.getJobs():
            build = item.current_build_set.getBuild(job)
            (result, url) = item.formatJobResult(job)
            # If child_jobs is being used to skip jobs, then the user
            # probably has an expectation that some jobs will be
            # skipped and doesn't need to see all of them.  Otherwise,
            # it may be a surprise and it may be better to include the
            # job in the report.
            if (build.error_detail and
                'Skipped due to child_jobs' in build.error_detail):
                skipped += 1
                continue
            if not job.voting:
                voting = ' (non-voting)'
            else:
                voting = ''

            if config and config.has_option(
                'zuul', 'report_times'):
                report_times = config.getboolean(
                    'zuul', 'report_times')
            else:
                report_times = True

            if report_times and build.end_time and build.start_time:
                dt = int(build.end_time - build.start_time)
                m, s = divmod(dt, 60)
                h, m = divmod(m, 60)
                if h:
                    elapsed = ' in %dh %02dm %02ds' % (h, m, s)
                elif m:
                    elapsed = ' in %dm %02ds' % (m, s)
                else:
                    elapsed = ' in %ds' % (s)
            else:
                elapsed = ''
            if build.error_detail:
                error = ' ' + build.error_detail
            else:
                error = ''
            name = job.name + ' '
            # TODO(mordred) The gerrit consumption interface depends on
            # something existing in the url field and don't have a great
            # behavior defined for url being none/missing. Put name into
            # the url field to match old behavior until we can deal with
            # the gerrit-side piece as well
            url = url or job.name
            # Pass user defined success_message deciding the build result
            # during result formatting
            success_message = job.success_message
            jobs_fields.append(
                (name, url, result, error, elapsed, voting, success_message))
        return jobs_fields, skipped

    def _formatItemReportJobs(self, item):
        # Return the list of jobs portion of the report
        ret = ''
        jobs_fields, skipped = self._getItemReportJobsFields(item)
        for job_fields in jobs_fields:
            ret += '- %s%s : %s%s%s%s\n' % job_fields[:6]
        if skipped:
            jobtext = 'job' if skipped == 1 else 'jobs'
            ret += 'Skipped %i %s\n' % (skipped, jobtext)
        return ret
