# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
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
from zuul.driver.gitea.giteamodel import GiteaEventFilter
from zuul.driver.util import scalar_or_list, to_list, make_regex, ZUUL_REGEX


class GiteaTrigger(BaseTrigger):
    name = 'gitea'
    log = logging.getLogger("zuul.GiteaTrigger")

    def getEventFilters(self, connection_name, trigger_conf, parse_context):
        efilters = []
        pcontext = parse_context
        for trigger in to_list(trigger_conf):
            with pcontext.confAttr(trigger, 'event') as attr:
                types = [make_regex(x, pcontext)
                         for x in to_list(attr)]
            with pcontext.confAttr(trigger, 'ref') as attr:
                refs = [make_regex(x, pcontext)
                        for x in to_list(attr)]
            with pcontext.confAttr(trigger, 'comment') as attr:
                comments = [make_regex(x, pcontext)
                            for x in to_list(attr)]

            f = GiteaEventFilter(
                connection_name=connection_name,
                trigger=self,
                types=types,
                actions=to_list(trigger.get('action')),
                comments=comments,
                refs=refs,
                states=to_list(trigger.get('state')),
            )
            efilters.append(f)

        return efilters


def getSchema():
    gitea_trigger = {
        v.Required('event'):
            scalar_or_list(v.Any(
                'gt_pull_request',
                'gt_pull_request_review',
                'gt_push')),
        'action': scalar_or_list(str),
        'comment': scalar_or_list(v.Any(ZUUL_REGEX, str)),
        'ref': scalar_or_list(v.Any(ZUUL_REGEX, str)),
        'state': scalar_or_list(str),
    }

    return gitea_trigger
