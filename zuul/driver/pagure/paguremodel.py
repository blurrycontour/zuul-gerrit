import re
import re2
from zuul.model import Change, TriggerEvent, EventFilter

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


class PagureCommonFilter(object):
    def __init__(self, *args, **kwargs):
        pass

    def matchesReviews(self, change):
        return True

    def matchesRequiredReviews(self, change):
        return True

    def matchesNoRejectReviews(self, change):
        return True

    def matchesStatuses(self, change):
        return True

    def matchesRequiredStatuses(self, change):
        return True

    def matchesNoRejectStatuses(self, change):
        return True


class PagureEventFilter(EventFilter, PagureCommonFilter):
    def __init__(self, trigger, types=[], branches=[], refs=[],
                 comments=[], actions=[], labels=[], unlabels=[],
                 states=[], statuses=[], required_statuses=[],
                 ignore_deletes=True):

        EventFilter.__init__(self, trigger)

        PagureCommonFilter.__init__(self, required_statuses=required_statuses)

        self._types = types
        self._branches = branches
        self._refs = refs
        self._comments = comments
        self.types = [re.compile(x) for x in types]
        self.branches = [re.compile(x) for x in branches]
        self.refs = [re.compile(x) for x in refs]
        self.comments = [re.compile(x) for x in comments]
        self.actions = actions
        self.labels = labels
        self.unlabels = unlabels
        self.states = states
        self.statuses = statuses
        self.required_statuses = required_statuses
        self.ignore_deletes = ignore_deletes

    def __repr__(self):
        ret = '<PagureEventFilter'

        if self._types:
            ret += ' types: %s' % ', '.join(self._types)
        if self._branches:
            ret += ' branches: %s' % ', '.join(self._branches)
        if self._refs:
            ret += ' refs: %s' % ', '.join(self._refs)
        if self.ignore_deletes:
            ret += ' ignore_deletes: %s' % self.ignore_deletes
        if self._comments:
            ret += ' comments: %s' % ', '.join(self._comments)
        if self.actions:
            ret += ' actions: %s' % ', '.join(self.actions)
        if self.labels:
            ret += ' labels: %s' % ', '.join(self.labels)
        if self.unlabels:
            ret += ' unlabels: %s' % ', '.join(self.unlabels)
        if self.states:
            ret += ' states: %s' % ', '.join(self.states)
        if self.statuses:
            ret += ' statuses: %s' % ', '.join(self.statuses)
        if self.required_statuses:
            ret += ' required_statuses: %s' % ', '.join(self.required_statuses)
        ret += '>'

        return ret

    def matches(self, event, change):
        # event types are ORed
        matches_type = False
        for etype in self.types:
            if etype.match(event.type):
                matches_type = True
        if self.types and not matches_type:
            return False

        # branches are ORed
        matches_branch = False
        for branch in self.branches:
            if branch.match(event.branch):
                matches_branch = True
        if self.branches and not matches_branch:
            return False

        # refs are ORed
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

        # comments are ORed
        matches_comment_re = False
        for comment_re in self.comments:
            if (event.comment is not None and
                comment_re.search(event.comment)):
                matches_comment_re = True
        if self.comments and not matches_comment_re:
            return False

        # actions are ORed
        matches_action = False
        for action in self.actions:
            if (event.action == action):
                matches_action = True
        if self.actions and not matches_action:
            return False

        # labels are ORed
        if self.labels and event.label not in self.labels:
            return False

        # unlabels are ORed
        if self.unlabels and event.unlabel not in self.unlabels:
            return False

        # states are ORed
        if self.states and event.state not in self.states:
            return False

        # statuses are ORed
        if self.statuses:
            status_found = False
            for status in self.statuses:
                if re2.fullmatch(status, event.status):
                    status_found = True
                    break
            if not status_found:
                return False

        if not self.matchesStatuses(change):
            return False

        return True
