# Copyright 2019 Smaato, Inc.
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

from zuul.trigger import BaseTrigger
from zuul.driver.util import scalar_or_list, to_list

from zuul.driver.bitbucket.bitbucketmodel import BitbucketEventFilter


class BitbucketTrigger(BaseTrigger):
    name = 'bitbucket'
    log = logging.getLogger('zuul.BitbucketTrigger')

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            f = BitbucketEventFilter(
                actions=to_list(trigger.get('action')),
                comments=to_list(trigger.get('comment')),
                branches=to_list(trigger.get('branch')),
                refs=to_list(trigger.get('ref')),
                trigger=self,
                types=to_list(trigger['event']),
            )
            efilters.append(f)

        return efilters


def getSchema():
    bitbucket_trigger = {
        'action': scalar_or_list(str),
        'branch': scalar_or_list(str),
        'comment': scalar_or_list(str),
        'ref': scalar_or_list(str),
        v.Required('event'): scalar_or_list(v.Any('bb-pr',
                                                  'bb-comment',
                                                  'bb-push',
                                                  'bb-tag')),
    }

    return bitbucket_trigger
