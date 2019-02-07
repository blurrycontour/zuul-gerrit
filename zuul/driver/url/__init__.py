import logging
import requests

from zuul.driver import Driver, SourceInterface
from zuul.model import RefFilter
from zuul.source import BaseSource


class URLDriver(Driver, SourceInterface):
    name = 'url'
    log = logging.getLogger("zuul.driver.url.URLDriver")

    def getSource(self, connection=None):
        return URLSource(self, connection)

    def getRequireSchema(self):
        require = {
            'url': str,
            'connection': str,
        }
        return require

    def getRejectSchema(self):
        return {}


class URLSource(BaseSource):
    name = 'url'
    log = logging.getLogger("zuul.driver.url.URLSource")

    def __init__(self, driver, *args):
        super(URLSource, self).__init__(
            driver, None, None, None)

    def getRefSha(self):
        raise NotImplementedError()

    def isMerged(self):
        raise NotImplementedError()

    def canMerge(self):
        raise NotImplementedError()

    def getChange(self):
        raise NotImplementedError()

    def getChangeByURL(self):
        raise NotImplementedError()

    def getChangesDependingOn(self):
        raise NotImplementedError()

    def getProjectOpenChanges(self):
        raise NotImplementedError()

    def getGitUrl(self):
        raise NotImplementedError()

    def getProject(self):
        raise NotImplementedError()

    def getProjectBranches(self):
        raise NotImplementedError()

    def getRequireFilters(self, config):

        f = URLRefFilter(
            connection_name=config['connection'],
            url=config['url'],
        )
        return [f]

    def getRejectFilters(self):
        raise NotImplementedError()

class URLRefFilter(RefFilter):
    name = 'url'
    log = logging.getLogger("zuul.driver.url.RefFilter")

    def __init__(self, connection_name, url):
        RefFilter.__init__(self, connection_name)
        self.url = url
        self.attr = 'ETag'
        self.url_attr_cache = None

    def __repr__(self):
        return '<URLRefFilter url: %s>' % self.url

    def matches(self, change=None):
        self.log.debug("Fetching %s" % self.url)
        headers = requests.get(self.url).headers
        attr_value = headers.get(self.attr)
        if self.url_attr_cache is None:
            # New attr - Only feed the cache
            self.log.debug(
                "No previous value for %s only feed the "
                "cache for: %s" % (self.url, self.attr))
            self.url_attr_cache = attr_value
            return False
        if attr_value == self.url_attr_cache:
            self.log.debug(
                "%s for %s has not changed" % (self.attr, self.url))
            return False
        self.log.debug("%s for %s, previous: %s, current: %s" % (
            self.attr, self.url, self.url_attr_cache, attr_value))
        self.log.info("Url at %s changed" % self.url)
        self.url_attr_cache = attr_value
        return True
