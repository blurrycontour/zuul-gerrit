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

    def report(self, item):
        """Publish messages to a topic via fedmsg."""

        self.log.debug("Report change %s, params %s" %
                       (item.change, self.config))
        message = {
            'zuul_ref': item.current_build_set.ref,
            'pipeline': item.pipeline.name,
            'project': item.change.project.name,
            'change': item.change.number,
            'patchset': item.change.patchset,
            'ref': item.change.refspec,
            'message': self._formatItemReport(
                item, with_jobs=False),
        }
        self.connection.publish(self.config['topic'], message)

        for job in item.getJobs():
            build = item.current_build_set.getBuild(job.name)
            if not build:
                # build hasn't began. The sql reporter can only send back
                # stats about builds. It doesn't understand how to store
                # information about the change.
                continue
            (result, url) = item.formatJobResult(job)

            message = {
                'uuid': build.uuid,
                'job_name': build.job.name,
                'result': result,
                'start_time': build.start_time,
                'end_time': build.end_time,
                'voting': build.job.voting,
                'log_url': url,
                'node_name': build.node_name,
            }
            topic = '%s.%s' % (self.config['topic'], 'job')
            self.connection.publish(topic, message)


def getSchema():
    fedmsg_reporter = v.Schema({
        'topic': str,
    })
    return fedmsg_reporter
