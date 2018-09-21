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
                branches=to_list(trigger.get('branch')),
                refs=to_list(trigger.get('ref')),
                comments=to_list(trigger.get('comment')),
                labels=to_list(trigger.get('label')),
                unlabels=to_list(trigger.get('unlabel')),
                states=to_list(trigger.get('state')),
                statuses=to_list(trigger.get('status')),
                required_statuses=to_list(trigger.get('require-status'))
            )
            efilters.append(f)

        return efilters

    def onPullRequest(self, payload):
        pass


def getSchema():
    pagure_trigger = {
        v.Required('event'):
            scalar_or_list(v.Any('pull_request',
                                 'pull_request_review',
                                 'push')),
        'action': scalar_or_list(str),
        'branch': scalar_or_list(str),
        'ref': scalar_or_list(str),
        'comment': scalar_or_list(str),
        'label': scalar_or_list(str),
        'unlabel': scalar_or_list(str),
        'state': scalar_or_list(str),
        'require-status': scalar_or_list(str),
        'status': scalar_or_list(str)
    }

    return pagure_trigger
