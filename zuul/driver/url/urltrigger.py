# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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

import voluptuous as v

from zuul.trigger import BaseTrigger
from zuul.driver.timer.urlmodel import URLEventFilter


class URLTrigger(BaseTrigger):
    name = 'url'

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            f = URLEventFilter(trigger=self,
                               delay=trigger['delay']
                               url=trigger['url']
                               attribute=trigger['attribute']
                               )

            efilters.append(f)

        return efilters


def getSchema():
    url_trigger = {
        v.Required('delay'): str,
        v.Required('url'): str,
        v.Required('attribute'): str,
        }
    return url_trigger
