import logging
import voluptuous as v
from zuul.driver.bitbucketserver.bitbucketservermodel import BitbucketServerEventFilter
from zuul.trigger import BaseTrigger
from zuul.driver.util import scalar_or_list, to_list


class BitbucketServerTrigger(BaseTrigger):
    name = 'bitbucket_server'
    log = logging.getLogger("zuul.trigger.BitbucketServerTrigger")

    def getEventFilters(self, trigger_config):
        efilters = []
        for trigger in to_list(trigger_config):
            f = BitbucketServerEventFilter(
                trigger=self,
                types=to_list(trigger['event']),
                actions=to_list(trigger.get('action')),
                comments=to_list(trigger.get('comment')),
                refs=to_list(trigger.get('ref')),
            )
            efilters.append(f)
        return efilters

    def onPullRequest(self, payload):
        pass


def getSchema():
    bitbucket_server_trigger = {
        v.Required('event'):
            scalar_or_list(
                v.Any(
                    'pull_request',
                    'repository',
                )),
        'action': scalar_or_list(str),
        'comment': scalar_or_list(str),
        'ref': scalar_or_list(str),
    }
    return bitbucket_server_trigger
