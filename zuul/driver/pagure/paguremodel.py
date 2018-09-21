import re
import re2
from zuul.model import Change, TriggerEvent, EventFilter, RefFilter

EMPTY_GIT_REF = '0' * 40  # git sha of all zeros, used during creates/deletes


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.project = None
        self.pr = None
        self.updated_at = None
        self.title = None
        self.reviews = []
        self.files = []
        self.labels = []

    def __repr__(self):
        pname = None
        if self.project and self.project.name:
            pname = self.project.name
        return '<Change 0x%x %s %s>' % (id(self), pname, self._id())

    def isUpdateOf(self, other):
        if (self.project == other.project and
            hasattr(other, 'number') and self.number == other.number and
            hasattr(other, 'updated_at') and
            self.updated_at > other.updated_at):
            return True
        return False


class PagureTriggerEvent(TriggerEvent):
    def __init__(self):
        super(PagureTriggerEvent, self).__init__()
        self.trigger_name = 'pagure'
        self.title = None
        self.action = None
        self.status = None

    def _repr(self):
        r = [super(PagureTriggerEvent, self)._repr()]
        if self.action:
            r.append("action:%s" % self.action)
        if self.status:
            r.append("status:%s" % self.status)
        r.append("project:%s" % self.canonical_project_name)
        if self.change_number:
            r.append("pr:%s" % self.change_number)
        return ' '.join(r)


class PagureEventFilter(EventFilter):
    def __init__(self, trigger, types=[], refs=[],
                 comments=[], actions=[], states=[], ignore_deletes=True):

        EventFilter.__init__(self, trigger)

        self._types = types
        self._refs = refs
        self._comments = comments
        self.types = [re.compile(x) for x in types]
        self.refs = [re.compile(x) for x in refs]
        self.comments = [re.compile(x) for x in comments]
        self.actions = actions
        self.states = states
        self.ignore_deletes = ignore_deletes

    def __repr__(self):
        ret = '<PagureEventFilter'

        if self._types:
            ret += ' types: %s' % ', '.join(self._types)
        if self._refs:
            ret += ' refs: %s' % ', '.join(self._refs)
        if self.ignore_deletes:
            ret += ' ignore_deletes: %s' % self.ignore_deletes
        if self._comments:
            ret += ' comments: %s' % ', '.join(self._comments)
        if self.actions:
            ret += ' actions: %s' % ', '.join(self.actions)
        if self.states:
            ret += ' states: %s' % ', '.join(self.states)
        ret += '>'

        return ret

    def matches(self, event, change):
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return False

        matches_ref = False
        if event.ref is not None:
            for ref in self.refs:
                if ref.match(event.ref):
                    matches_ref = True
        if self.refs and not matches_ref:
            return False
        if self.ignore_deletes and event.newrev == EMPTY_GIT_REF:
            # If the updated ref has an empty git sha (all 0s),
            # then the ref is being deleted
            return False

        matches_comment_re = False
        for comment_re in self.comments:
            if (event.comment is not None and
                comment_re.search(event.comment)):
                matches_comment_re = True
        if self.comments and not matches_comment_re:
            return False

        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return False

        if self.states and event.state not in self.states:
            return False

        return True


class PagureRefFilter(RefFilter):
    def __init__(self, connection_name):
        RefFilter.__init__(self, connection_name)

    def __repr__(self):
        ret = '<PagureRefFilter connection_name: %s>' % self.connection_name
        return ret

    def matches(self, change):
        return True
