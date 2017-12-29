# Copyright 2015 Rackspace Australia
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


class SlackReporter(BaseReporter):
    """Sends off reports to slack channels."""

    name = 'slack'
    log = logging.getLogger("zuul.SlackReporter")

    def report(self, item):
        """Send message to associated channels."""
        message = self._formatItemReport(item)
        subject = self.config.get('subject', self.connection.subject)
        subject = subject.format(**vars(item))
        channels = self.config.get('channel')
        if isinstance(channels, str):
            channels = [channels]
        pchannels = self.config.get(
            'project-channels', {}).get(item.change.project.name, [])
        if isinstance(pchannels, str):
            pchannels = [pchannels]
        channels += pchannels
        for channel in channels:
            ts_cache = self.connection.thread_cache.get(item, {})
            thread_ts = ts_cache.get(channel)
            update_cache = thread_ts is None
            self.log.debug("Reporting {change} to {channel}".format(
                change=item.change, channel=channel))
            initial_msg = self.connection.client.api_call(
                "chat.postMessage",
                channel=channel,
                as_user=True,
                text=subject,
                thread_ts=thread_ts,
            )
            if not initial_msg['ok']:
                self.log.error(
                    'Failed sending message for {change}: {error}'.format(
                        change=item.change, error=initial_msg['error']))
                continue
            if update_cache:
                thread_ts = initial_msg['ts']
                ts_cache = self.connection.thread_cache.get(item, {})
                ts_cache[channel] = thread_ts
                self.connection.thread_cache[item] = ts_cache
            self.connection.client.api_call(
                "chat.postMessage",
                channel=channel,
                as_user=True,
                text=message,
                thread_ts=thread_ts)
        self.log.info("Reported {change} to {channels}".format(
            change=item.change, channels=channels))


def getSchema():
    slack_reporter = v.Schema({
        v.Optional('subject'): str,
        v.Optional('channel'): v.Any([str], str),
        v.Optional('project-channels'): {str: v.Any([str], str)},
    })
    return slack_reporter
