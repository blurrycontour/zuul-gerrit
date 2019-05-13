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

from zuul.trigger import BaseTrigger
from zuul.driver.bitbucket.model import BitbucketEventFilter


class BitbucketTrigger(BaseTrigger):
    name = 'bitbucket'
    log = logging.getLogger('zuul.BitbucketTrigger')

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            f = BitbucketEventFilter(
                trigger=self,
                types=to_list(trigger['event']),
                refs=to_list(trigger.get('ref')),
            )
            efilters.append(f)

        return efilters

def getSchema():
    bitbucket_trigger = {
        v.Required('event'):
            scalar_or_list(v.Any('bb-pr-updated')),
        'project': str,
        'pr': str,
    }

    return bitbucket_trigger
