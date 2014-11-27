# Copyright 2012 Hewlett-Packard Development Company, L.P.
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
import voluptuous
from zuul.model import EventFilter
from zuul.trigger import BaseTrigger


class GerritTrigger(BaseTrigger):
    name = 'gerrit'
    log = logging.getLogger("zuul.trigger.Gerrit")
    replication_timeout = 300
    replication_retry_interval = 5

    def __init__(self, trigger_config={}):
        super(GerritTrigger, self).__init__(trigger_config)

    def getEventFilters(self, trigger_conf):
        def toList(item):
            if not item:
                return []
            if isinstance(item, list):
                return item
            return [item]

        efilters = []
        if 'gerrit' in trigger_conf:
            for trigger in toList(trigger_conf['gerrit']):
                approvals = {}
                for approval_dict in toList(trigger.get('approval')):
                    for k, v in approval_dict.items():
                        approvals[k] = v
                # Backwards compat for *_filter versions of these args
                comments = toList(trigger.get('comment'))
                if not comments:
                    comments = toList(trigger.get('comment_filter'))
                emails = toList(trigger.get('email'))
                if not emails:
                    emails = toList(trigger.get('email_filter'))
                usernames = toList(trigger.get('username'))
                if not usernames:
                    usernames = toList(trigger.get('username_filter'))
                f = EventFilter(
                    trigger=self,
                    types=toList(trigger['event']),
                    branches=toList(trigger.get('branch')),
                    refs=toList(trigger.get('ref')),
                    event_approvals=approvals,
                    comments=comments,
                    emails=emails,
                    usernames=usernames,
                    required_any_approval=(
                        toList(trigger.get('require-any-approval'))
                        + toList(trigger.get('require-approval'))
                    ),
                    required_all_approvals=toList(
                        trigger.get('require-all-approvals')
                    ),
                )
                efilters.append(f)

        return efilters


def validate_trigger(trigger_data):
    """Validates the layout's trigger data."""
    events_with_ref = ('ref-updated', )
    for event in trigger_data['gerrit']:
        if event['event'] not in events_with_ref and event.get('ref', False):
            raise voluptuous.Invalid(
                "The event %s does not include ref information, Zuul cannot "
                "use ref filter 'ref: %s'" % (event['event'], event['ref']))
