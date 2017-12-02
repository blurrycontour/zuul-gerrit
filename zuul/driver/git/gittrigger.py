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
from zuul.trigger import BaseTrigger
from zuul.driver.git.gitmodel import GitEventFilter
from zuul.driver.util import scalar_or_list, to_list


class GitTrigger(BaseTrigger):
    name = 'git'
    log = logging.getLogger("zuul.GitTrigger")

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            f = GitEventFilter(
                trigger=self,
                types=to_list(trigger['event']),
                refs=to_list(trigger.get('ref')),
                ignore_deletes=trigger.get(
                    'ignore-deletes', True)
            )
            efilters.append(f)

        return efilters


def validate_conf(trigger_conf):
    """Validates the layout's trigger data."""
    events_with_ref = ('ref-updated', )
    for event in trigger_conf:
        if event['event'] not in events_with_ref and event.get('ref', False):
            raise v.Invalid(
                "The event %s does not include ref information, Zuul cannot "
                "use ref filter 'ref: %s'" % (event['event'], event['ref']))


def getSchema():
    git_trigger = {
        v.Required('event'):
            scalar_or_list(v.Any('ref-updated')),
        'ref': scalar_or_list(str),
        'ignore-deletes': bool,
    }

    return git_trigger
