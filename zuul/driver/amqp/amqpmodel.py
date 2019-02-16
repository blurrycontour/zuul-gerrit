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
import re2

from zuul.model import EventFilter, TriggerEvent


class AMQPTriggerEvent(TriggerEvent):
    def __repr__(self):
        return '<AMQPTriggerEvent %s address:%s body:%s>' % (
            self.type,
            self.address,
            self.body)


class AMQPFilter(EventFilter):
    log = logging.getLogger("zuul.AMQPFilter")

    def __init__(self, trigger, address, body):
        super().__init__(trigger)
        self.address = [re2.compile(x) for x in address]
        self.body = {}
        for k, v in body.items():
            self.body[k] = re2.compile(v)

    def __repr__(self):
        ret = '<AMQPFilter'
        if self.body:
            ret += ' body: %s' % ', '.join(
                ['%s:%s' % a for a in self.body.items()])
        ret += '>'
        return ret

    def matches(self, event, change):
        if event.type != 'message-published':
            return False

        matches_address = False
        for address in self.address:
            if address.match(event.address):
                matches_address = True
                break
        if self.address and not matches_address:
            return False

        matches_body = True
        for k, v in self.body.items():
            if not v.match(event.body.get(k, '')):
                matches_body = False
                break
        if self.body and not matches_body:
            return False

        return True
