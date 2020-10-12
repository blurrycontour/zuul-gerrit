import re

from zuul.model import TriggerEvent, EventFilter, RefFilter


class BitbucketServerTriggerEvent(TriggerEvent):
    def __init__(self):
        super(BitbucketServerTriggerEvent, self).__init__()
        self.trigger_name = 'bitbucketserver'
        self.title = None
        self.action = None
        self.change_number = None


class BitbucketServerEventFilter(EventFilter):
    def __init__(
            self, trigger, types=None, actions=None,
            comments=None, refs=None, ignore_deletes=True):
        super(BitbucketServerEventFilter, self).__init__(self)
        self._types = types or []
        self.types = [re.compile(x) for x in self._types]
        self.actions = actions or []
        self._comments = comments or []
        self.comments = [re.compile(x) for x in self._comments]
        self._refs = refs or []
        self.refs = [re.compile(x) for x in self._refs]
        self.ignore_deletes = ignore_deletes

    def matches(self, event, change):
        return False


# The RefFilter should be understood as RequireFilter (it maps to
# pipeline requires definition)
class BitbucketServerRefFilter(RefFilter):
    def __init__(self, connection_name, open=None, merged=None, approved=None):
        RefFilter.__init__(self, connection_name)
        self.open = open
        self.merged = merged
        self.approved = approved

    def matches(self, change):
        return False
