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
import voluptuous as v
from zuul.model import EventFilter
from zuul.trigger import BaseTrigger


class GerritTrigger(BaseTrigger):
    name = 'gerrit'
    log = logging.getLogger("zuul.trigger.Gerrit")

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
                    for key, val in approval_dict.items():
                        approvals[key] = val
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


def validate_conf(trigger_conf):
    """Validates the layout's trigger data."""
    events_with_ref = ('ref-updated', )
    for event in trigger_conf:
        if event['event'] not in events_with_ref and event.get('ref', False):
            raise v.Invalid(
                "The event %s does not include ref information, Zuul cannot "
                "use ref filter 'ref: %s'" % (event['event'], event['ref']))


def getSchema():
    def toList(x):
        return v.Any([x], x)
    variable_dict = v.Schema({}, extra=True)

    require_approval = v.Schema({'username': str,
                                 'email-filter': str,
                                 'email': str,
                                 'older-than': str,
                                 'newer-than': str,
                                 }, extra=True)

    gerrit_trigger = {
        v.Required('event'):
            toList(v.Any('patchset-created',
                         'draft-published',
                         'change-abandoned',
                         'change-restored',
                         'change-merged',
                         'comment-added',
                         'ref-updated')),
        'comment_filter': toList(str),
        'comment': toList(str),
        'email_filter': toList(str),
        'email': toList(str),
        'username_filter': toList(str),
        'username': toList(str),
        'branch': toList(str),
        'ref': toList(str),
        'approval': toList(variable_dict),
        'require-all-approvals': toList(require_approval),
        'require-any-approval': toList(require_approval),
        'require-approval': toList(require_approval),
    }

    return gerrit_trigger
