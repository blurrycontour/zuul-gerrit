import logging

from zuul.source import BaseSource

from zuul.driver.bitbucketserver.bitbucketservermodel import BitbucketServerRefFilter


class BitbucketServerSource(BaseSource):
    name = 'bitbucketserver'
    log = logging.getLogger("zuul.source.BitbucketServerSource")

    def __init__(self, driver, connection, config=None):
        super(BitbucketServerSource, self).__init__(driver, connection, 'todo', config)

    def getRefSha(self, project, ref):
        """Return a sha for a given project ref."""
        raise NotImplementedError()

    def waitForRefSha(self, project, ref, old_sha=''):
        """Block until a ref shows up in a given project."""
        raise NotImplementedError()

    def isMerged(self, change, head=None):
        """Determine if change is merge."""
        raise NotImplementedError()

    def canMerge(self, change, allow_needs, event=None):
        """Determine if change can merge."""
        raise NotImplementedError()

    def postConfig(self):
        """Called after configuration has been processed."""
        raise NotImplementedError()

    def getChange(self, event, refresh=False):
        return self.connection.getChange(event, refresh)

    def getChangeByURL(self, url, event):
        raise NotImplementedError()

    def getChangesDependingOn(self, change, projects, tenant):
        raise NotImplementedError()

    def getCachedChanges(self):
        raise NotImplementedError()

    def getProject(self, name):
        raise NotImplementedError()

    def getProjectBranches(self, project, tenant):
        raise NotImplementedError()

    def getProjectOpenChanges(self, project):
        """Get the open changes for a project."""
        raise NotImplementedError()

    def updateChange(self, change, history=None):
        """Update information for a change."""
        raise NotImplementedError()

    def getGitUrl(self, project):
        """Get the git url for a project."""
        raise NotImplementedError()

    def getGitwebUrl(self, project, sha=None):
        """Get the git-web url for a project."""
        raise NotImplementedError()

    def getRequireFilters(self, config):
        f = BitbucketServerRefFilter(
            connection_name=self.connection.connection_name,
            open=config.get('open'),
            merged=config.get('merged'),
            approved=config.get('approved')
        )
        return [f]

    def getRejectFilters(self, config):
        raise NotImplementedError()

    def getRefForChange(self, change):
        raise NotImplementedError()


# Require model
def getRequireSchema():
    require = {
        'open': bool,
        'merged': bool,
        'approved': bool,
    }
    return require


def getRejectSchema():
    reject = {}
    return reject
