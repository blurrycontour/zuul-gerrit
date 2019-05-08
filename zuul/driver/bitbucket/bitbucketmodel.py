from zuul.model import Change


class PullRequest(Change):
    def __init__(self, project):
        super(PullRequest, self).__init__(project)
        self.project = None
        self.pr = None
        self.updatedDate = None
        self.title = None
        self.reviews = []
        self.files = []
        self.labels = []

    def __eq__(self, obj):
        return isinstance(obj, PullRequest) and self.project == obj.project \
            and self.id == obj.id and self.updatedDate == obj.updatedDate

    def isUpdateOf(self, other):
        if (self.project == other.project and
                hasattr(other, 'id') and self.id == other.id and
                hasattr(other, 'patchset') and
                self.patchset != other.patchset and
                hasattr(other, 'updatedDate') and
                self.updatedDate > other.updatedDate):
            return True
        return False
