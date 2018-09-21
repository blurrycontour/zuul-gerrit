import logging
import voluptuous as v
from zuul.trigger import BaseTrigger
from zuul.driver.pagure.paguremodel import PagureEventFilter
from zuul.driver.util import scalar_or_list, to_list


class PagureTrigger(BaseTrigger):
    name = 'pagure'
    log = logging.getLogger("zuul.trigger.PagureTrigger")

    def getEventFilters(self, trigger_config):
        efilters = []
        for trigger in to_list(trigger_config):
            f = PagureEventFilter(
                trigger=self,
                types=to_list(trigger['event']),
                actions=to_list(trigger.get('action')),
                refs=to_list(trigger.get('ref')),
                comments=to_list(trigger.get('comment')),
                states=to_list(trigger.get('state')),
            )
            efilters.append(f)

        return efilters

    def onPullRequest(self, payload):
        pass


def getSchema():
    pagure_trigger = {
        v.Required('event'):
            scalar_or_list(v.Any('pg_pull_request',
                                 'pg_pull_request_review',
                                 'push')),
        'action': scalar_or_list(str),
        'ref': scalar_or_list(str),
        'comment': scalar_or_list(str),
        'state': scalar_or_list(str),  # could be 'approved or request_changes'
    }

    return pagure_trigger
