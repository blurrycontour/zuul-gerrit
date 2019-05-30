

import re2

from zuul.model import EventFilter, TriggerEvent


class SlackEventFilter(EventFilter):
    def __init__(self, trigger, types=[], channels=[]):
        EventFilter.__init__(self, trigger)

        self._types = types
        self.types = [re2.compile(x) for x in types]
        self.channels = channels

    def __repr__(self):
        ret = '<SlackEventFilter'

        if self._types:
            ret += ' types: {}'.format(self._types)

        if self._channels:
            ret += ' chnanels {}'.format(self.channels)

        ret += '>'

        return ret

    def matches(self, event, change):
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return False

        matches_channels = False
        for channel in self.channels:
            if event.channel == channel:
                matches_channels = True
        if self.channels and not matches_channels:
            return False

        return True


class SlackTriggerEvent(TriggerEvent):
    def __init__(self):
        super(SlackTriggerEvent, self).__init__()
        self.channels = None
