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
import time
import voluptuous as v

from zuul.reporter import BaseReporter, safe_template_value


class MQTTReporter(BaseReporter):
    """Publish messages to a topic via mqtt"""

    name = 'mqtt'
    log = logging.getLogger("zuul.MQTTReporter")

    def report(self, item):
        self.log.debug("Report change %s, params %s" %
                       (item.change, self.config))
        message = {
            'timestamp': time.time(),
            'action': self._action,
            'tenant': item.pipeline.tenant.name,
            'zuul_ref': item.current_build_set.ref,
            'pipeline': item.pipeline.name,
            'project': item.change.project.name,
            'branch': getattr(item.change, 'branch', ''),
            'change_url': item.change.url,
            'change': getattr(item.change, 'number', ''),
            'patchset': getattr(item.change, 'patchset', ''),
            'ref': getattr(item.change, 'ref', ''),
            'message': self._formatItemReport(
                item, with_jobs=False),
            'enqueue_time': item.enqueue_time,
            'buildset': {
                'uuid': item.current_build_set.uuid,
                'builds': []
            },
        }
        for job in item.getJobs():
            job_informations = {
                'job_name': job.name,
                'voting': job.voting,
            }
            build = item.current_build_set.getBuild(job.name)
            if build:
                # Report build data if available
                (result, url) = item.formatJobResult(job)
                job_informations.update({
                    'uuid': build.uuid,
                    'start_time': build.start_time,
                    'end_time': build.end_time,
                    'execute_time': build.execute_time,
                    'log_url': url,
                    'result': result,
                })
            message['buildset']['builds'].append(job_informations)

        topic = self.safeFormatTemplate(self.config['topic'], item)
        if topic is not None:
            self.connection.publish(
                topic, message, qos=self.config.get('qos', 0))


def qosValue(value):
    if not isinstance(value, int):
        raise v.Invalid("qos is not a integer")
    if value not in (0, 1, 2):
        raise v.Invalid("qos can only be 0, 1 or 2")
    return value


def getSchema():
    return v.Schema({v.Required('topic'): safe_template_value,
                     'qos': qosValue})
