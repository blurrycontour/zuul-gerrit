# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

from zuul.model import EventFilter
from zuul.trigger import BaseTrigger


class GithubTrigger(BaseTrigger):
    name = 'github'
    log = logging.getLogger("zuul.Timer")

    def _toList(item):
        if not item:
            return []
        if isinstance(item, list):
            return item
        return [item]

    def getEventFilters(self, trigger_config):
        try:
            config = trigger_config['github']
        except KeyError:
            return

        efilters = []
        for trigger in self._toList(config):
            types = trigger_config.get('event', None)
            f = EventFilter(trigger=self,
                            types=self._toList(types))
            efilters.append(f)

        return efilters

    def onPullRequest(self, payload):
        pass
