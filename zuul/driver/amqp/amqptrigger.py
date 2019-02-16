# Copyright 2019 Red Hat, Inc.
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

from zuul.driver.amqp.amqpmodel import AMQPFilter
from zuul.driver.util import scalar_or_list, to_list
from zuul.trigger import BaseTrigger


class AMQPTrigger(BaseTrigger):
    name = 'amqp'
    log = logging.getLogger("zuul.AMQPTrigger")

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            body = trigger.get('body', {})
            efilters.append(AMQPFilter(
                trigger=self,
                address=to_list(trigger.get('address', [])),
                body=body,
            ))
        return efilters


def getSchema():
    return {
        v.Required('event'): 'message-published',
        'address': scalar_or_list(str),
        'body': v.Schema(dict),
    }
