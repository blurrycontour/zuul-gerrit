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
import threading
import voluptuous
from zuul.model import EventFilter, TriggerEvent
from zuul.trigger import BaseTrigger


class GerritEventConnector(threading.Thread):
    """Move events from Gerrit to the scheduler."""

    log = logging.getLogger("zuul.GerritEventConnector")

    def __init__(self, gerrit, sched, trigger, source):
        super(GerritEventConnector, self).__init__()
        self.daemon = True
        self.gerrit = gerrit
        self.sched = sched
        self.trigger = trigger
        self.source = source
        self._stopped = False

    def stop(self):
        self._stopped = True
        self.gerrit.addEvent(None)

    def _handleEvent(self):
        data = self.gerrit.getEvent()
        if self._stopped:
            return
        event = TriggerEvent()
        event.type = data.get('type')
        event.trigger_name = self.trigger.name
        change = data.get('change')
        if change:
            event.project_name = change.get('project')
            event.branch = change.get('branch')
            event.change_number = change.get('number')
            event.change_url = change.get('url')
            patchset = data.get('patchSet')
            if patchset:
                event.patch_number = patchset.get('number')
                event.refspec = patchset.get('ref')
            event.approvals = data.get('approvals', [])
            event.comment = data.get('comment')
        refupdate = data.get('refUpdate')
        if refupdate:
            event.project_name = refupdate.get('project')
            event.ref = refupdate.get('refName')
            event.oldrev = refupdate.get('oldRev')
            event.newrev = refupdate.get('newRev')
        # Map the event types to a field name holding a Gerrit
        # account attribute. See Gerrit stream-event documentation
        # in cmd-stream-events.html
        accountfield_from_type = {
            'patchset-created': 'uploader',
            'draft-published': 'uploader',  # Gerrit 2.5/2.6
            'change-abandoned': 'abandoner',
            'change-restored': 'restorer',
            'change-merged': 'submitter',
            'merge-failed': 'submitter',  # Gerrit 2.5/2.6
            'comment-added': 'author',
            'ref-updated': 'submitter',
            'reviewer-added': 'reviewer',  # Gerrit 2.5/2.6
        }
        try:
            event.account = data.get(accountfield_from_type[event.type])
        except KeyError:
            self.log.error("Received unrecognized event type '%s' from Gerrit.\
                    Can not get account information." % event.type)
            event.account = None

        if event.change_number:
            # Call _getChange for the side effect of updating the
            # cache.  Note that this modifies Change objects outside
            # the main thread.
            self.source._getChange(event.change_number,
                                   event.patch_number,
                                   refresh=True)

        self.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except:
                self.log.exception("Exception moving Gerrit event:")
            finally:
                self.gerrit.eventDone()


class GerritTrigger(BaseTrigger):
    name = 'gerrit'
    log = logging.getLogger("zuul.trigger.Gerrit")

    def __init__(self, gerrit, config, sched, source):
        self.sched = sched
        # TODO(jhesketh): Make 'gerrit' come from a connection (rather than the
        #                 source)
        # TODO(jhesketh): Remove the requirement for a gerrit source (currently
        #                 it is needed so on a trigger event the cache is
        #                 updated. However if we share a connection object the
        #                 cache could be stored there)
        self.config = config
        self.gerrit_connector = GerritEventConnector(gerrit, sched, self,
                                                     source)
        self.gerrit_connector.start()

    def stop(self):
        self.gerrit_connector.stop()
        self.gerrit_connector.join()

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

    def postConfig(self):
        pass


def validate_trigger(trigger_data):
    """Validates the layout's trigger data."""
    events_with_ref = ('ref-updated', )
    for event in trigger_data['gerrit']:
        if event['event'] not in events_with_ref and event.get('ref', False):
            raise voluptuous.Invalid(
                "The event %s does not include ref information, Zuul cannot "
                "use ref filter 'ref: %s'" % (event['event'], event['ref']))
