

import voluptuous as v

from zuul.trigger import BaseTrigger
from zuul.driver.util import to_list

from zuul.driver.slack.slackmodel import SlackEventFilter


class SlackTrigger(BaseTrigger):
    name = 'slack'

    def getEventFilters(self, trigger_conf):
        filters = []
        for trigger in to_list(trigger_conf):
            f = SlackEventFilter(trigger=self,
                                 types=['slack'],
                                 channels=to_list(trigger.get('channel')))
            filters.append(f)

        return filters


def getSchema():
    slack_trigger = {v.Required('channel'): str}
    return slack_trigger
