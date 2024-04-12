# Copyright 2014 Rackspace Australia
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import abc
import logging

from zuul.lib.logutil import get_annotated_logger
from zuul import model


class ReadOnlyBranchCacheError(RuntimeError):
    pass


class BaseConnection(object, metaclass=abc.ABCMeta):
    """Base class for connections.

    A connection is a shared object that sources, triggers and reporters can
    use to speak with a remote API without needing to establish a new
    connection each time or without having to authenticate each time.

    Multiple instances of the same connection may exist with different
    credentials, for example, thus allowing for different pipelines to operate
    on different Gerrit installations or post back as a different user etc.

    Connections can implement their own public methods. Required connection
    methods are validated by the {trigger, source, reporter} they are loaded
    into. For example, a trigger will likely require some kind of query method
    while a reporter may need a review method."""

    log = logging.getLogger('zuul.BaseConnection')

    def __init__(self, driver, connection_name, connection_config):
        # connection_name is the name given to this connection in zuul.ini
        # connection_config is a dictionary of config_section from zuul.ini for
        # this connection.
        # __init__ shouldn't make the actual connection in case this connection
        # isn't used in the layout.
        self.driver = driver
        self.connection_name = connection_name
        self.connection_config = connection_config
        self.sched = None

    def logEvent(self, event):
        log = get_annotated_logger(self.log, event.zuul_event_id)
        log.debug('Scheduling event from {connection}: {event}'.format(
            connection=self.connection_name,
            event=event))
        try:
            if self.sched.statsd:
                self.sched.statsd.incr(
                    'zuul.event.{driver}.{event}'.format(
                        driver=self.driver.name, event=event.type))
                self.sched.statsd.incr(
                    'zuul.event.{driver}.{connection}.{event}'.format(
                        driver=self.driver.name,
                        connection=self.connection_name,
                        event=event.type))
        except Exception:
            self.log.exception("Exception reporting event stats")

    def onLoad(self, zk_client, component_registry):
        pass

    def onStop(self):
        pass

    def registerScheduler(self, sched) -> None:
        self.sched = sched

    def cleanupCache(self):
        """Clean up the connection cache.

        This allows a connection to perform periodic cleanup actions of
        the cache, e.g. garbage collection.
        """
        pass

    def maintainCache(self, relevant, max_age):
        """Remove stale changes from the cache.

        This lets the user supply a list of change cache keys that are
        still in use.  Anything in our cache that isn't in the supplied
        list and is older than the given max. age (in seconds) should
        be safe to remove from the cache."""
        pass

    def getWebController(self, zuul_web):
        """Return a cherrypy web controller to register with zuul-web.

        :param zuul.web.ZuulWeb zuul_web:
            Zuul Web instance.
        :returns: A `zuul.web.handler.BaseWebController` instance.
        """
        return None

    def getEventQueue(self):
        """Return the event queue for this connection.

        :returns: A `zuul.zk.event_queues.ConnectionEventQueue` instance
                  or None.
        """
        return None

    def validateWebConfig(self, config, connections):
        """Validate web config.

        If there is a fatal error, the method should raise an exception.

        :param config:
           The parsed config object.
        :param zuul.lib.connections.ConnectionRegistry connections:
           Registry of all configured connections.
        """
        return False

    def toDict(self):
        """Return public information about the connection
        """
        return {
            "name": self.connection_name,
            "driver": self.driver.name,
        }


class ZKBranchCacheMixin:
    # Expected to be defined by the connection and to be an instance
    # of BranchCache
    _branch_cache = None
    read_only = False

    @abc.abstractmethod
    def isBranchProtected(self, project_name, branch_name,
                          zuul_event_id):
        """Return if the branch is protected or None if the branch is unknown.

        :param str project_name:
            The name of the project.
        :param str branch_name:
            The name of the branch.
        :param zuul_event_id:
            Unique id associated to the handled event.
        """
        pass

    @abc.abstractmethod
    def _fetchProjectBranches(self, project, required_flags):
        """Perform a remote query to determine the project's branches.

        Connection subclasses should implement this method.

        :param model.Project project:
            The project.
        :param set(BranchFlag) required_flags:
            Which flags need to be valid in the result set.

        :returns: A list of BranchInfo objects
        """

    @abc.abstractmethod
    def _getProjectBranchesRequiredFlags(self, exclude_unprotected,
                                         exclude_locked):
        """Calculate the set of required branch flags needed to filter the
        branches as specified.

        Connection subclasses should implement this method.

        :param bool exclude_unprotected:
            Whether to exclude unprotected branches
        :param bool exclude_locked:
            Whether to exclude locked branches

        :returns: A set of BranchFlag objects
        """

    @abc.abstractmethod
    def _filterProjectBranches(self, branch_infos, exclude_unprotected,
                               exclude_locked):
        """Filter branches according to the specified criteria

        Connection subclasses should implement this method.

        :param list(BranchInfo) branch_infos:
            A list of BranchInfo objects previously supplied by
            _fetchProjectBranches
        :param bool exclude_unprotected:
            Whether to exclude unprotected branches
        :param bool exclude_locked:
            Whether to exclude locked branches

        :returns: A list of BranchInfo objects
        """

    def _fetchProjectMergeModes(self, project):
        """Perform a remote query to determine the project's supported merge
           modes.

        Connection subclasses should implement this method if they are
        able to determine which merge modes apply for a project.  The
        default implemantion returns that all merge modes are valid.

        :param model.Project project:
            The project.

        :returns: A list of merge modes as model IDs.

        """
        return model.ALL_MERGE_MODES

    def _fetchProjectDefaultBranch(self, project):
        """Perform a remote query to determine the project's default branch.

        Connection subclasses should implement this method if they are
        able to determine the upstream default branch for a project.  The
        default implemantion returns 'master' for now and will likely change
        to return something else if and when the git default changes.

        :param model.Project project:
            The project.

        :returns: The name of the default branch.

        """
        return 'master'

    def clearConnectionCacheOnBranchEvent(self, event):
        """Update event and clear connection cache if needed.

        This checks whether the event created or deleted a branch so
        that Zuul may know to perform a reconfiguration on the
        project. Drivers must call this method when a branch event is
        received.

        :param event:
            The event, inherit from `zuul.model.TriggerEvent` class.
        """
        if event.oldrev == '0' * 40:
            event.branch_created = True
        elif event.newrev == '0' * 40:
            event.branch_deleted = True
        else:
            event.branch_updated = True

        project = self.source.getProject(event.project_name)
        if event.branch:
            if event.branch_deleted:
                # We currently cannot determine if a deleted branch was
                # protected so we need to assume it was. GitHub/GitLab don't
                # allow deletion of protected branches but we don't get a
                # notification about branch protection settings. Thus we don't
                # know if branch protection has been disabled before deletion
                # of the branch.
                # FIXME(tobiash): Find a way to handle that case
                self.updateProjectBranches(project)
            elif event.branch_created:
                # In GitHub, a new branch never can be protected
                # because that needs to be configured after it has
                # been created.  Other drivers could optimize this,
                # but for the moment, implement the lowest common
                # denominator and clear the cache so that we query.
                self.updateProjectBranches(project)
            event.branch_cache_ltime = self._branch_cache.ltime
        return event

    def updateProjectBranches(self, project):
        """Update the branch cache for the project.

        :param zuul.model.Project project:
            The project for which the branches are returned.
        """
        # Figure out which queries we have a cache for

        required_flags = self._branch_cache.getProjectCompletedFlags(
            project.name)
        if required_flags:
            # Update them if we have them
            valid_flags, branch_infos = self._fetchProjectBranches(
                project, required_flags)
            self._branch_cache.setProjectBranches(
                project.name, valid_flags, branch_infos)

        merge_modes = self._fetchProjectMergeModes(project)
        self._branch_cache.setProjectMergeModes(
            project.name, merge_modes)

        default_branch = self._fetchProjectDefaultBranch(project)
        self._branch_cache.setProjectDefaultBranch(
            project.name, default_branch)
        self.log.info("Updated branches for %s" % project.name)

    def getProjectBranches(self, project, tenant, min_ltime=-1):
        """Get the branch names for the given project.

        :param zuul.model.Project project:
            The project for which the branches are returned.
        :param zuul.model.Tenant tenant:
            The related tenant.
        :param int min_ltime:
            The minimum ltime to determine if we need to refresh the cache.

        :returns: The list of branch names.
        """
        exclude_unprotected = tenant.getExcludeUnprotectedBranches(project)
        exclude_locked = tenant.getExcludeLockedBranches(project)
        branches = None

        required_flags = self._getProjectBranchesRequiredFlags(
            exclude_unprotected, exclude_locked)
        if self._branch_cache:
            try:
                branches = self._branch_cache.getProjectBranches(
                    project.name, required_flags, min_ltime)
                if branches is not None:
                    branches = [b.name for b in self._filterProjectBranches(
                        branches, exclude_unprotected, exclude_locked)]
            except LookupError:
                if self.read_only:
                    # A scheduler hasn't attempted to fetch them yet
                    raise ReadOnlyBranchCacheError(
                        "Will not fetch project branches as read-only is set")
                else:
                    branches = None

        if branches is not None:
            return sorted(branches)
        elif self.read_only:
            # A scheduler has previously attempted a fetch, but got
            # the None due to an error; we can't retry since we're
            # read-only.
            raise RuntimeError(
                "Will not fetch project branches as read-only is set")

        # Above we calculated a set of flags needed to answer the
        # query.  If the fetch below fails, we will mark that set of
        # flags as failed in the ProjectInfo structure.  However, if
        # the fetch below succeeds, it can supply its own set of valid
        # flags that we will record as successful.  This lets the
        # driver indicate that the returned results include more data
        # than strictly necessary (ie, protected+locked and not just
        # protected).
        try:
            valid_flags, branch_infos = self._fetchProjectBranches(
                project, required_flags)
        except Exception:
            # We weren't able to get the branches.  We need to tell
            # future schedulers to try again but tell zuul-web that we
            # tried and failed.  Set the branches to None to indicate
            # that we have performed a fetch and retrieved no data.  Any
            # time we encounter None in the cache, we will try again.
            if self._branch_cache:
                self._branch_cache.setProjectBranches(
                    project.name, required_flags, None)
            raise
        self.log.info("Got branches for %s" % project.name)

        if self._branch_cache:
            self._branch_cache.setProjectBranches(
                project.name, valid_flags, branch_infos)

        return sorted(bi.name for bi in branch_infos)

    def getProjectMergeModes(self, project, tenant, min_ltime=-1):
        """Get the merge modes for the given project.

        :param zuul.model.Project project:
            The project for which the merge modes are returned.
        :param zuul.model.Tenant tenant:
            The related tenant.
        :param int min_ltime:
            The minimum ltime to determine if we need to refresh the cache.

        :returns: The list of merge modes by model id.
        """
        merge_modes = None

        if self._branch_cache:
            try:
                merge_modes = self._branch_cache.getProjectMergeModes(
                    project.name, min_ltime)
            except LookupError:
                if self.read_only:
                    # A scheduler hasn't attempted to fetch them yet
                    raise ReadOnlyBranchCacheError(
                        "Will not fetch merge modes as read-only is set")
                else:
                    merge_modes = None

        if merge_modes is not None:
            return merge_modes
        elif self.read_only:
            # A scheduler has previously attempted a fetch, but got
            # the None due to an error; we can't retry since we're
            # read-only.
            raise RuntimeError(
                "Will not fetch merge_modes as read-only is set")

        # We need to perform a query
        try:
            merge_modes = self._fetchProjectMergeModes(project)
        except Exception:
            # We weren't able to get the merge modes.  We need to tell
            # future schedulers to try again but tell zuul-web that we
            # tried and failed.  Set the merge modes to None to indicate
            # that we have performed a fetch and retrieved no data.  Any
            # time we encounter None in the cache, we will try again.
            if self._branch_cache:
                self._branch_cache.setProjectMergeModes(
                    project.name, None)
            raise
        self.log.info("Got merge modes for %s" % project.name)

        if self._branch_cache:
            self._branch_cache.setProjectMergeModes(
                project.name, merge_modes)

        return merge_modes

    def getProjectDefaultBranch(self, project, tenant, min_ltime=-1):
        """Get the default branch for the given project.

        :param zuul.model.Project project:
            The project for which the default branch is returned.
        :param zuul.model.Tenant tenant:
            The related tenant.
        :param int min_ltime:
            The minimum ltime to determine if we need to refresh the cache.

        :returns: The name of the default branch.
        """
        default_branch = None

        if self._branch_cache:
            try:
                default_branch = self._branch_cache.getProjectDefaultBranch(
                    project.name, min_ltime)
            except LookupError:
                if self.read_only:
                    # A scheduler hasn't attempted to fetch it yet
                    raise ReadOnlyBranchCacheError(
                        "Will not fetch default branch as read-only is set")
                else:
                    default_branch = None

        if default_branch is not None:
            return default_branch
        elif self.read_only:
            # A scheduler has previously attempted a fetch, but got
            # the None due to an error; we can't retry since we're
            # read-only.
            raise RuntimeError(
                "Will not fetch default branch as read-only is set")

        # We need to perform a query
        try:
            default_branch = self._fetchProjectDefaultBranch(project)
        except Exception:
            # We weren't able to get the default branch.  We need to tell
            # future schedulers to try again but tell zuul-web that we
            # tried and failed.  Set the default branch to None to indicate
            # that we have performed a fetch and retrieved no data.  Any
            # time we encounter None in the cache, we will try again.
            if self._branch_cache:
                self._branch_cache.setProjectDefaultBranch(
                    project.name, None)
            raise
        self.log.info("Got default branch for %s: %s", project.name,
                      default_branch)

        if self._branch_cache:
            self._branch_cache.setProjectDefaultBranch(
                project.name, default_branch)

        return default_branch

    def checkBranchCache(self, project_name, event, protected=None):
        """Update the cache for a project when a branch event is processed

        This method must be called when a branch event is processed: if the
        event references a branch and the unprotected branches are excluded,
        the branch protection status could have been changed.

        :params str project_name:
            The project name.
        :params event:
            The event, inherit from `zuul.model.TriggerEvent` class.
        :params protected:
            If defined the caller already knows if the branch is protected
            so the query can be skipped.
        """
        if protected is None:
            protected = self.isBranchProtected(project_name, event.branch,
                                               zuul_event_id=event)
        if protected is not None:
            required_flags = self._getProjectBranchesRequiredFlags(
                exclude_unprotected=True, exclude_locked=False)

            branches = self._branch_cache.getProjectBranches(
                project_name, required_flags, default=None)

            if not branches:
                branches = []

            branches = [b.name for b in branches]

            update = False
            if (event.branch in branches) and (not protected):
                update = True
            if (event.branch not in branches) and (protected):
                update = True
            if update:
                self.log.info("Project %s branch %s protected state "
                              "changed to %s",
                              project_name, event.branch, protected)
                self._branch_cache.setProtected(project_name, event.branch,
                                                protected)
                event.branch_cache_ltime = self._branch_cache.ltime

            event.branch_protected = protected
        else:
            # This can happen if the branch was deleted in GitHub/GitLab.
            # In this case we assume that the branch COULD have
            # been protected before. The cache update is handled by
            # the push event, so we don't touch the cache here
            # again.
            event.branch_protected = True

    def clearBranchCache(self, projects=None):
        """Clear the branch cache

        In case the branch cache gets out of sync with the source,
        this method can be called to clear it and force querying the
        source the next time the cache is used.
        """
        self._branch_cache.clear(projects)


class ZKChangeCacheMixin:
    # Expected to be defined by the connection and to be an instance
    # that implements the AbstractChangeCache API.
    _change_cache = None

    def cleanupCache(self):
        self._change_cache.cleanup()

    def maintainCache(self, relevant, max_age):
        self._change_cache.prune(relevant, max_age)

    def updateChangeAttributes(self, change, **attrs):
        def _update_attrs(c):
            for name, value in attrs.items():
                setattr(c, name, value)
        self._change_cache.updateChangeWithRetry(change.cache_stat.key,
                                                 change, _update_attrs)

    def estimateCacheDataSize(self):
        return self._change_cache.estimateDataSize()
