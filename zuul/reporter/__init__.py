# Copyright 2014 Rackspace Australia
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

import six


@six.add_metaclass(abc.ABCMeta)
class BaseReporter(object):
    """Base class for reporters.

    Defines the exact public methods that must be supplied.
    """

    def __init__(self, reporter_config={}, sched=None, connection=None):
        self.reporter_config = reporter_config
        self.sched = sched
        self.connection = connection

    def stop(self):
        """Stop the reporter."""

    @abc.abstractmethod
    def report(self, source, pipeline, item, message=None, params=[]):
        """Send the compiled report message."""

    def getSubmitAllowNeeds(self, params):
        """Get a list of code review labels that are allowed to be
        "needed" in the submit records for a change, with respect
        to this queue.  In other words, the list of review labels
        this reporter itself is likely to set before submitting.
        """
        return []

    def postConfig(self):
        """Run tasks after configuration is reloaded"""

    def _formatItemReport(self, pipeline, item):
        """Format a report from the given items. Usually to provide results to
        a reporter taking free-form text."""
        ret = ''

        if item.dequeued_needing_change:
            ret += 'This change depends on a change that failed to merge.\n'
        elif not pipeline.didMergerSucceed(item):
            ret += pipeline.merge_failure_message
        else:
            if pipeline.didAllJobsSucceed(item):
                ret += pipeline.success_message + '\n\n'
            else:
                ret += pipeline.failure_message + '\n\n'
            ret += self._formatItemReportJobs(pipeline, item)

        if pipeline.footer_message:
            ret += '\n' + pipeline.footer_message

        return ret

    def _formatItemReportJobs(self, pipeline, item):
        # Return the list of jobs portion of the report
        ret = ''

        if self.sched.config.has_option('zuul', 'url_pattern'):
            url_pattern = self.sched.config.get('zuul', 'url_pattern')
        else:
            url_pattern = None

        for job in pipeline.getJobs(item):
            build = item.current_build_set.getBuild(job.name)
            result = build.result
            pattern = url_pattern
            if result == 'SUCCESS':
                if job.success_message:
                    result = job.success_message
                if job.success_pattern:
                    pattern = job.success_pattern
            elif result == 'FAILURE':
                if job.failure_message:
                    result = job.failure_message
                if job.failure_pattern:
                    pattern = job.failure_pattern
            if pattern:
                url = pattern.format(change=item.change,
                                     pipeline=pipeline,
                                     job=job,
                                     build=build)
            else:
                url = build.url or job.name
            if not job.voting:
                voting = ' (non-voting)'
            else:
                voting = ''

            if self.sched.config and self.sched.config.has_option(
                'zuul', 'report_times'):
                report_times = self.sched.config.getboolean(
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
            name = ''
            if self.sched.config.has_option('zuul', 'job_name_in_report'):
                if self.sched.config.getboolean('zuul',
                                                'job_name_in_report'):
                    name = job.name + ' '
            ret += '- %s%s : %s%s%s\n' % (name, url, result, elapsed,
                                          voting)
        return ret
