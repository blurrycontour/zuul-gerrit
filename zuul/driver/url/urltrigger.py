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

import voluptuous as v

from zuul.trigger import BaseTrigger
from zuul.driver.url.urlmodel import URLEventFilter
from zuul.driver.util import to_list


class URLTrigger(BaseTrigger):
    name = 'url'

    def getEventFilters(self, trigger_conf):
        efilters = []
        for trigger in to_list(trigger_conf):
            f = URLEventFilter(trigger=self,
                               _type='url',
                               time=trigger['time'],
                               url=trigger['url'],
                               header_field=trigger['header_field'],
                               )
            efilters.append(f)
        return efilters


def getSchema():
    url_trigger = {
        v.Required('time'): str,
        v.Required('url'): str,
        v.Required('header_field'): str,
    }
    return url_trigger
