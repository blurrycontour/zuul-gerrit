# Copyright 2014 Rackspace Australia
# Copyright 2021 BMW Group
# Copyright 2021, 2024 Acme Gating, LLC
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

import collections
from enum import Enum
import logging
import json
from functools import reduce
from operator import ior

from zuul.zk.zkobject import ZKContext, ShardedZKObject
from zuul.zk.locks import (
    SessionAwareReadLock,
    SessionAwareWriteLock,
    locked as zk_locked
)
from zuul import model
from zuul.zk.components import COMPONENT_REGISTRY

from kazoo.exceptions import NoNodeError

# Default marker to raise an exception on cache miss in getProjectBranches()
RAISE_EXCEPTION = object()


# These flags should be the purview of the drivers, but we need to
# know about them in order to support backwards compatability to
# MODEL_API < 27.  In the future, we should be able to make these
# driver-specific and have driver-specific subclasses of BranchInfo,
# etc.
class BranchFlag(Enum):
    PRESENT = 0x1
    PROTECTED = 0x2
    LOCKED = 0x4


# A helper method for the branch cache below.
def return_default(default, project_name):
    if default is RAISE_EXCEPTION:
        raise LookupError(
            f"No branches for project {project_name}")
    return default


class BranchInfo:
    def __init__(self, name, present=None, protected=None, locked=None):
        self.name = name
        # These are tri-state: None means indeterminate, true or false
        # are definitive.
        self.present = present
        self.protected = protected
        self.locked = locked

    def update(self, other):
        if other.present is not None:
            self.present = other.present
        if other.protected is not None:
            self.protected = other.protected
        if other.locked is not None:
            self.locked = other.locked

    def toDict(self):
        # This doesn't really return a dict, but like other toDict
        # methods, it returns the object that will be encoded into
        # JSON.  It just happens we don't need a full dict for this.
        flags = 0
        valid_flags = 0
        for f in self.flags:
            flags |= f.value
        for f in self.valid_flags:
            valid_flags |= f.value
        return [flags, valid_flags]

    @property
    def flags(self):
        flags = set()
        if self.present:
            flags.add(BranchFlag.PRESENT)
        if self.protected:
            flags.add(BranchFlag.PROTECTED)
        if self.locked:
            flags.add(BranchFlag.LOCKED)
        return flags

    @property
    def valid_flags(self):
        # If a flag is None, then we don't know it for this branch so
        # we consider it invalid.
        valid_flags = set()
        if self.present is not None:
            valid_flags.add(BranchFlag.PRESENT)
        if self.protected is not None:
            valid_flags.add(BranchFlag.PROTECTED)
        if self.locked is not None:
            valid_flags.add(BranchFlag.LOCKED)
        return valid_flags

    @classmethod
    def fromDict(cls, name, data):
        o = cls(name)
        flags, valid_flags = data
        if valid_flags & BranchFlag.PRESENT.value:
            o.present = bool(flags & BranchFlag.PRESENT.value)
        if valid_flags & BranchFlag.PROTECTED.value:
            o.protected = bool(flags & BranchFlag.PROTECTED.value)
        if valid_flags & BranchFlag.LOCKED.value:
            o.locked = bool(flags & BranchFlag.LOCKED.value)
        return o


class ProjectInfo:
    """Store branch cache project information in ZK

    If a project is absent from the cache, it needs to be queried from
    the source.
    """
    def __init__(self, name, merge_modes=None, default_branch=None):
        self.name = name
        self.merge_modes = merge_modes
        self.default_branch = default_branch
        self.branches = {}
        # The set of flags we have performed queries for:
        self.completed_flags = set()
        # If there was an error fetching the branches for a given set
        # of flags, the failure will be recorded here:
        self.failed_flags = set()

    def toDict(self):
        return {
            'merge_modes': self.merge_modes,
            'default_branch': self.default_branch,
            'branches': {b.name: b.toDict() for b in self.branches.values()},
            'flags': [
                reduce(ior, [x.value for x in self.completed_flags], 0),
                reduce(ior, [x.value for x in self.failed_flags], 0),
            ],
        }

    @classmethod
    def fromDict(cls, name, data):
        o = cls(name)
        o.merge_modes = data['merge_modes']
        o.default_branch = data['default_branch']
        o.branches = {
            name: BranchInfo.fromDict(name, bdata)
            for name, bdata in data['branches'].items()
        }
        completed_flags = data['flags'][0]
        failed_flags = data['flags'][1]

        for flag in BranchFlag:
            if flag.value & completed_flags:
                o.completed_flags.add(flag)
            if flag.value & failed_flags:
                o.failed_flags.add(flag)
        return o


class BranchCacheZKObject(ShardedZKObject):
    """Store the branch cache in ZK

    If a project is absent from the dict, it needs to be queried from
    the source.

    If there was an error fetching the branches, None will be stored
    as a sentinel value.
    """

    # We can always recreate data if necessary, so go ahead and
    # truncate when we update so we avoid corrupted data.
    truncate_on_create = True

    def getPath(self):
        return self._path

    def __init__(self):
        super().__init__()
        self._set(
            projects={},
        )

    def serialize(self, context):
        if COMPONENT_REGISTRY.model_api < 27:
            data = self.serialize_old()
        else:
            data = self.serialize_new()
        return json.dumps(data, sort_keys=True).encode("utf8")

    def serialize_new(self):
        return {
            "projects": {p.name: p.toDict() for p in self.projects.values()},
        }

    def serialize_old(self):
        protected = {}
        remainder = {}
        merge_modes = {}
        default_branch = {}

        for pi in self.projects.values():
            merge_modes[pi.name] = pi.merge_modes
            default_branch[pi.name] = pi.default_branch
            if BranchFlag.PROTECTED in pi.completed_flags:
                pl = protected[pi.name] = []
            elif BranchFlag.PROTECTED in pi.failed_flags:
                pl = protected[pi.name] = None
            else:
                pl = None
            if BranchFlag.PRESENT in pi.completed_flags:
                rl = remainder[pi.name] = []
            elif BranchFlag.PRESENT in pi.failed_flags:
                rl = remainder[pi.name] = None
            else:
                rl = None
            for bi in pi.branches.values():
                if bi.protected:
                    if pl is not None:
                        pl.append(bi.name)
                    elif rl is not None:
                        rl.append(bi.name)
                elif rl is not None:
                    rl.append(bi.name)

        return {
            "protected": protected,
            "remainder": remainder,
            "merge_modes": merge_modes,
            "default_branch": default_branch,
        }

    def deserialize(self, raw, context):
        data = super().deserialize(raw, context)
        if "protected" in data:
            # MODEL_API < 27
            self.deserialize_old(data)
        else:
            self.deserialize_new(data)
        return data

    def deserialize_new(self, data):
        projects = {}
        for project_name, project_data in data['projects'].items():
            projects[project_name] = ProjectInfo.fromDict(
                project_name, project_data)
        data['projects'] = projects

    def deserialize_old(self, data):
        if "merge_modes" not in data:
            # MODEL_API < 11
            data["merge_modes"] = collections.defaultdict(
                lambda: model.ALL_MERGE_MODES)
        if "default_branch" not in data:
            # MODEL_API < 16
            data["default_branch"] = collections.defaultdict(
                lambda: 'master')
        projects = {}
        for project_name, branches in data['protected'].items():
            project_info = ProjectInfo(
                project_name,
                data['merge_modes'].get(project_name, model.ALL_MERGE_MODES),
                data['default_branch'].get(project_name, 'master'))
            projects[project_name] = project_info
            if branches is None:
                project_info.failed_flags.add(BranchFlag.PROTECTED)
            elif branches:
                project_info.completed_flags.add(BranchFlag.PROTECTED)
                for branch_name in branches:
                    project_info.branches[branch_name] = BranchInfo(
                        branch_name, protected=True)
        for project_name, branches in data['remainder'].items():
            project_info = projects.get(project_name)
            if project_info is None:
                project_info = ProjectInfo(
                    project_name,
                    data['merge_modes'].get(project_name,
                                            model.ALL_MERGE_MODES),
                    data['default_branch'].get(project_name, 'master'))
                projects[project_name] = project_info
                if branches is None:
                    project_info.failed_flags.add(BranchFlag.PRESENT)
                elif branches:
                    project_info.completed_flags.add(BranchFlag.PRESENT)
                    for branch_name in branches:
                        # Create a branchinfo object
                        project_info.branches[branch_name] = BranchInfo(
                            branch_name, present=True)
        data.clear()
        data['projects'] = projects

    def _save(self, context, data, create=False):
        super()._save(context, data, create)
        zstat = context.client.exists(self.getPath())
        self._set(_zstat=zstat)

    def _load(self, context, path=None):
        super()._load(context, path)
        zstat = context.client.exists(self.getPath())
        self._set(_zstat=zstat)


class BranchCache:
    def __init__(self, zk_client, connection, component_registry):
        self.log = logging.getLogger(
            f"zuul.BranchCache.{connection.connection_name}")

        self.connection = connection

        cname = self.connection.connection_name
        base_path = f'/zuul/cache/connection/{cname}/branches'
        lock_path = f'{base_path}/lock'
        data_path = f'{base_path}/data'

        self.rlock = SessionAwareReadLock(zk_client.client, lock_path)
        self.wlock = SessionAwareWriteLock(zk_client.client, lock_path)

        # TODO: standardize on a stop event for connections and add it
        # to the context.
        self.zk_context = ZKContext(zk_client, self.wlock, None, self.log)

        with (self.zk_context as ctx,
              zk_locked(self.wlock)):
            try:
                self.cache = BranchCacheZKObject.fromZK(
                    ctx, data_path, _path=data_path)
            except NoNodeError:
                self.cache = BranchCacheZKObject.new(
                    ctx, _path=data_path)

    def clear(self, projects=None):
        """Clear the cache"""
        with (zk_locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):
            if projects is None:
                self.cache.projects.clear()
            else:
                for p in projects:
                    self.cache.projects.pop(p, None)

    def _getRequiredFlags(self, exclude_unprotected, exclude_locked):
        required_flags = set()
        if exclude_unprotected:
            required_flags.add(BranchFlag.PROTECTED)
        if exclude_locked:
            required_flags.add(BranchFlag.LOCKED)
        if not required_flags:
            required_flags = {BranchFlag.PRESENT}
        return required_flags

    def _getProjectCompletedFlags(self, project_name):
        try:
            project_info = self.cache.projects[project_name]
        except KeyError:
            return set()
        return project_info.completed_flags

    def getProjectBranches(self, project_name, required_flags,
                           min_ltime=-1, default=RAISE_EXCEPTION):
        """Get the branch names for the given project.

        Checking the branch cache we need to distinguish three different
        cases:

            1. cache miss (not queried yet)
            2. cache hit (including empty list of branches)
            3. error when fetching branches

        If the cache doesn't contain any branches for the project and no
        default value is provided a LookupError is raised.

        If there was an error fetching the branches, the return value
        will be None.

        Otherwise the list of branches will be returned.

        :param str project_name:
            The project for which the branches are returned.
        :param bool required_flags:
            The branch flags we must have completed queries for in order
            for the cache to be considered valid.
        :param int min_ltime:
            The minimum cache ltime to consider the cache valid.
        :param any default:
            Optional default value to return if no cache entry exits.

        :returns: The list of branch names, or None if there was
            an error when fetching the branches.
        """
        if self.ltime < min_ltime:
            with (zk_locked(self.rlock),
                  self.zk_context as ctx):
                self.cache.refresh(ctx)

        project_info = None
        try:
            project_info = self.cache.projects[project_name]
        except KeyError:
            return return_default(default, project_name)

        # We've definitely stored a failure, so return that.
        if project_info is None:
            return None

        # Determine if we have enough info to answer the question
        if not (required_flags.issubset(project_info.completed_flags)):
            # We don't have the data, either because we haven't
            # queried it or the query failed.  Figure out which.
            if (required_flags & project_info.failed_flags):
                return None
            return return_default(default, project_name)

        # We have the necessary info for this filtering.
        return list(project_info.branches.values())

    def setProjectBranches(self, project_name,
                           valid_flags, branch_infos):
        """Set the branch names for the given project.

        Use None as a sentinel value for the branches to indicate that
        there was a fetch error.

        :param str project_name:
            The project for the branches.
        :param set(int) queries:
            The queries this list of branches is able to satisfy.
        :param list[str] branches:
            The list of branches or None to indicate a fetch error.
        """

        with (zk_locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):

            project_info = self.cache.projects.get(project_name)
            if project_info is None:
                project_info = ProjectInfo(project_name)
                self.cache.projects[project_name] = project_info

            if branch_infos is None:
                # We're storing an error, set the bits accordingly
                for flag in valid_flags:
                    project_info.failed_flags.add(flag)
                    project_info.completed_flags.discard(flag)
                return

            # Set the bits indicating a good query.
            for flag in valid_flags:
                project_info.failed_flags.discard(flag)
                project_info.completed_flags.add(flag)

            # Add or update branch info
            for branch_info in branch_infos:
                existing = project_info.branches.get(branch_info.name)
                if existing:
                    existing.update(branch_info)
                else:
                    project_info.branches[branch_info.name] = branch_info

            # Delete any existing branches which we would expect to be
            # in the results but aren't.  At the time of writing, this
            # isn't strictly necessary beacuse we clear the branch
            # cache on branch deletion, but this may enable us to
            # change that in the future.
            valid_branches = set([bi.name for bi in branch_infos])
            for branch_name in list(project_info.branches.keys()):
                if branch_name in valid_branches:
                    continue
                branch_info = project_info.branches[branch_name]
                if branch_info.valid_flags.issubset(valid_flags):
                    del project_info.branches[branch_name]

    def setProtected(self, project_name, branch, protected):
        """Correct the protection state of a branch.

        This may be called if a branch has changed state without us
        receiving an explicit event.
        """

        with (zk_locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):

            project_info = self.cache.projects.get(project_name)
            if project_info is None:
                project_info = ProjectInfo(project_name)
                self.cache.projects[project_name] = project_info

            branch_info = project_info.branches.get(branch)
            if branch_info is None:
                branch_info = BranchInfo(branch)
                project_info.branches[branch] = branch_info

            branch_info.protected = protected

    def getProjectMergeModes(self, project_name,
                             min_ltime=-1, default=RAISE_EXCEPTION):
        """Get the merge modes for the given project.

        Checking the branch cache we need to distinguish three different
        cases:

            1. cache miss (not queried yet)
            2. cache hit (including empty list of merge modes)
            3. error when fetching merge modes

        If the cache doesn't contain any merge modes for the project and no
        default value is provided a LookupError is raised.

        If there was an error fetching the merge modes, the return value
        will be None.

        Otherwise the list of merge modes will be returned.

        :param str project_name:
            The project for which the merge modes are returned.
        :param int min_ltime:
            The minimum cache ltime to consider the cache valid.
        :param any default:
            Optional default value to return if no cache entry exits.

        :returns: The list of merge modes by model id, or None if there was
            an error when fetching the merge modes.
        """
        if self.ltime < min_ltime:
            with zk_locked(self.rlock):
                self.cache.refresh(self.zk_context)

        project_info = None
        try:
            project_info = self.cache.projects[project_name]
        except KeyError:
            return return_default(default, project_name)

        if project_info is None:
            return None

        return project_info.merge_modes

    def setProjectMergeModes(self, project_name, merge_modes):
        """Set the supported merge modes for the given project.

        Use None as a sentinel value for the merge modes to indicate
        that there was a fetch error.

        :param str project_name:
            The project for the merge modes.
        :param list[int] merge_modes:
            The list of merge modes (by model ID) or None.

        """

        with zk_locked(self.wlock):
            with self.cache.activeContext(self.zk_context):
                project_info = self.cache.projects.get(project_name)
                if project_info is None:
                    project_info = ProjectInfo(project_name)
                project_info.merge_modes = merge_modes

    def getProjectDefaultBranch(self, project_name,
                                min_ltime=-1, default=RAISE_EXCEPTION):
        """Get the default branch for the given project.

        Checking the branch cache we need to distinguish three different
        cases:

            1. cache miss (not queried yet)
            2. cache hit (including unknown default branch)
            3. error when fetching default branch

        If the cache doesn't contain a default branch for the project
        and no default value is provided a LookupError is raised.

        If there was an error fetching the default branch, the return
        value will be None.

        Otherwise the default branch will be returned.

        :param str project_name:
            The project for which the default branch is returned.
        :param int min_ltime:
            The minimum cache ltime to consider the cache valid.
        :param any default:
            Optional default value to return if no cache entry exits.

        :returns: The name of the default branch or None if there was
            an error when fetching it.

        """
        if self.ltime < min_ltime:
            with zk_locked(self.rlock):
                self.cache.refresh(self.zk_context)

        project_info = None
        try:
            project_info = self.cache.projects[project_name]
        except KeyError:
            return return_default(default, project_name)

        if project_info is None:
            return None

        return project_info.default_branch

    def setProjectDefaultBranch(self, project_name, default_branch):
        """Set the upstream default branch for the given project.

        Use None as a sentinel value for the default branch to indicate
        that there was a fetch error.

        :param str project_name:
            The project for the default branch.
        :param str default_branch:
            The default branch or None.

        """

        with zk_locked(self.wlock):
            with self.cache.activeContext(self.zk_context):
                project_info = self.cache.projects.get(project_name)
                if project_info is None:
                    project_info = ProjectInfo(project_name)
                project_info.default_branch = default_branch

    @property
    def ltime(self):
        return self.cache._zstat.last_modified_transaction_id
