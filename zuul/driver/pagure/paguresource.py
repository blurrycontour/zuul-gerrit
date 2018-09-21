import logging
import voluptuous as v

from zuul.source import BaseSource
from zuul.model import Project

from zuul.driver.util import scalar_or_list


class PagureSource(BaseSource):
    name = 'pagure'
    log = logging.getLogger("zuul.source.PagureSource")

    def __init__(self, driver, connection, config=None):
        hostname = connection.canonical_hostname
        super(PagureSource, self).__init__(driver, connection,
                                           hostname, config)

    def getRefSha(self, project, ref):
        """Return a sha for a given project ref."""
        raise NotImplementedError()

    def waitForRefSha(self, project, ref, old_sha=''):
        """Block until a ref shows up in a given project."""
        raise NotImplementedError()

    def isMerged(self, change, head=None):
        """Determine if change is merged."""
        raise NotImplementedError()

    def canMerge(self, change, allow_needs):
        """Determine if change can merge."""
        if not change.number:
            # Not a pull request, considering merged.
            return True
        return self.connection.canMerge(change, allow_needs)

    def postConfig(self):
        """Called after configuration has been processed."""
        raise NotImplementedError()

    def getChange(self, event, refresh=False):
        return self.connection.getChange(event, refresh)

    def getChangeByURL(self, url):
        raise NotImplementedError()

    def getChangesDependingOn(self, change, projects, tenant):
        raise NotImplementedError()

    def getCachedChanges(self):
        return self.connection._change_cache.values()

    def getProject(self, name):
        p = self.connection.getProject(name)
        if not p:
            p = Project(name, self)
            self.connection.addProject(p)
        return p

    def getProjectBranches(self, project, tenant):
        return self.connection.getProjectBranches(project, tenant)

    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""
        raise NotImplementedError()

    def updateChange(self, change, history=None):
        """Update information for a change."""
        raise NotImplementedError()

    def getGitUrl(self, project):
        """Get the git url for a project."""
        return self.connection.getGitUrl(project)

    def getGitwebUrl(self, project, sha=None):
        """Get the git-web url for a project."""
        raise NotImplementedError()

    def _ghTimestampToDate(self, timestamp):
        raise NotImplementedError()

    def getRequireFilters(self, config):
        raise NotImplementedError()

    def getRejectFilters(self, config):
        raise NotImplementedError()

    def getRefForChange(self, change):
        raise NotImplementedError()


review = v.Schema({'username': str,
                   'email': str,
                   'older-than': str,
                   'newer-than': str,
                   'type': str,
                   'permission': v.Any('read', 'write', 'admin'),
                   })


def getRequireSchema():
    require = {'status': scalar_or_list(str),
               'review': scalar_or_list(review),
               'open': bool,
               'merged': bool,
               'current-patchset': bool,
               'label': scalar_or_list(str)}
    return require


def getRejectSchema():
    reject = {'status': scalar_or_list(str),
              'review': scalar_or_list(review),
              'open': bool,
              'merged': bool,
              'current-patchset': bool,
              'label': scalar_or_list(str)}
    return reject
