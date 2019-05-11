# Copyright 2019 BMW Group
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

from zuul.model import TriggerEvent


def get_annotated_logger(logger, event):
    if event is None:
        return logger
    if isinstance(event, TriggerEvent):
        event_id = event.zuul_event_id
    else:
        event_id = event
    return EventIdLogAdapter(logger, {'event_id': event_id})


class EventIdLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        event_id = kwargs.get('extra', {}).get('event_id')
        if event_id is not None:
            msg = '[e: %s] %s' % (event_id, msg)
        return msg, kwargs
