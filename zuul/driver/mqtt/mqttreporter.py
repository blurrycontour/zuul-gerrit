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


class MQTTReporter(BaseReporter):
    """Publish messages to a topic via mqtt"""

    name = 'mqtt'
    log = logging.getLogger("zuul.MQTTReporter")

    def report(self, item):
        self.log.debug("Report change %s, params %s" %
                       (item.change, self.config))
        message = {
            'zuul_ref': item.current_build_set.ref,
            'pipeline': item.pipeline.name,
            'project': item.change.project.name,
            'branch': item.change.branch,
            'change_url': item.change.url,
            'change': item.change.number,
            'patchset': item.change.patchset,
            'ref': getattr(item.change, 'ref', ''),
            'message': self._formatItemReport(
                item, with_jobs=False),
            'buildset': []
        }
        for job in item.getJobs():
            build = item.current_build_set.getBuild(job.name)
            if not build:
                # build hasn't began. The mqtt reporter can only send back
                # stats about builds. It doesn't understand how to store
                # information about the change.
                continue
            (result, url) = item.formatJobResult(job)

            message['buildset'].append({
                'uuid': build.uuid,
                'job_name': build.job.name,
                'result': result,
                'start_time': build.start_time,
                'end_time': build.end_time,
                'voting': build.job.voting,
                'log_url': url,
                'node_name': build.node_name,
            })
        topic = None
        try:
            topic = self.config['topic'].format(
                tenant=item.pipeline.layout.tenant.name,
                pipeline=item.pipeline.name,
                project=item.change.project.name,
                branch=item.change.branch,
                change=getattr(item.change, 'number', None),
                patchset=getattr(item.change, 'patchset', None),
                ref=getattr(item.change, 'ref', None))
        except Exception:
            self.log.exception("Error while formatting MQTT topic %s:"
                               % self.config['topic'])
        if topic is not None:
            self.connection.publish(
                topic, message, qos=self.config.get('qos', 0))


def topicValue(value):
    if not isinstance(value, str):
        raise v.Invalid("topic is not a string")
    try:
        value.format(
            tenant='test',
            pipeline='test',
            project='test',
            branch='test',
            change='test',
            patchset='test',
            ref='test')
    except KeyError as e:
        raise v.Invalid("topic component %s is invalid" % str(e))
    return value


def qosValue(value):
    if not isinstance(value, int):
        raise v.Invalid("qos is not a integer")
    if value not in (0, 1, 2):
        raise v.Invalid("qos can only be 0, 1 or 2")
    return value


def getSchema():
    return v.Schema({v.Required('topic'): topicValue, 'qos': qosValue})
