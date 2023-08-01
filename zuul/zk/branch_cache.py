# Copyright 2014 Rackspace Australia
# Copyright 2021 BMW Group
# Copyright 2021 Acme Gating, LLC
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
import logging
import json

from zuul.zk.zkobject import ZKContext, ShardedZKObject
from zuul.zk.locks import SessionAwareReadLock, SessionAwareWriteLock, locked
from zuul.zk.components import COMPONENT_REGISTRY
from zuul import model

from kazoo.exceptions import NoNodeError

# Default marker to raise an exception on cache miss in getProjectBranches()
RAISE_EXCEPTION = object()


class BranchCacheZKObject(ShardedZKObject):
    """Store the branch cache in ZK

    There are two projects dictionaries, protected and remainder.

    Each is project_name:str -> branches:list.

    The protected dictionary contains only the protected branches.

    The remainder dictionary contains any other branches.

    If there has never been a query that included unprotected
    branches, the projects key will not be present in the remaider
    dictionary.  If there has never been a query that excluded
    unprotected branches, then the protected dictionary will not have
    the project's key.

    If a project is absent from the dict, it needs to be queried from
    the source.

    If there was an error fetching the branches, None will be stored
    as a sentinel value.

    When performing an exclude_unprotected query, remove any duplicate
    branches from remaider to save space.  When determining the full
    list of branches, combine both lists.
    """

    # We can always recreate data if necessary, so go ahead and
    # truncate when we update so we avoid corrupted data.
    truncate_on_create = True

    def getPath(self):
        return self._path

    def __init__(self):
        super().__init__()
        self._set(protected={},
                  remainder={},
                  merge_modes={})

    def serialize(self, context):
        data = {
            "protected": self.protected,
            "remainder": self.remainder,
        }
        # This is mostly here to enable unit tests of upgrades, it's
        # safe to move into the dict above at any time.
        if (COMPONENT_REGISTRY.model_api >= 11):
            data["merge_modes"] = self.merge_modes
        return json.dumps(data, sort_keys=True).encode("utf8")

    def deserialize(self, raw, context):
        data = super().deserialize(raw, context)
        # MODEL_API < 11
        if "merge_modes" not in data:
            data["merge_modes"] = collections.defaultdict(
                lambda: model.ALL_MERGE_MODES)
        return data

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
              locked(self.wlock)):
            try:
                self.cache = BranchCacheZKObject.fromZK(
                    ctx, data_path, _path=data_path)
            except NoNodeError:
                self.cache = BranchCacheZKObject.new(
                    ctx, _path=data_path)

    def clear(self, projects=None):
        """Clear the cache"""
        with (locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):
            if projects is None:
                self.cache.protected.clear()
                self.cache.remainder.clear()
                self.cache.merge_modes.clear()
            else:
                for p in projects:
                    self.cache.protected.pop(p, None)
                    self.cache.remainder.pop(p, None)
                    self.cache.merge_modes.pop(p, None)

    def getProjectBranches(self, project_name, exclude_unprotected,
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
        :param bool exclude_unprotected:
            Whether to return all or only protected branches.
        :param int min_ltime:
            The minimum cache ltime to consider the cache valid.
        :param any default:
            Optional default value to return if no cache entry exits.

        :returns: The list of branch names, or None if there was
            an error when fetching the branches.
        """
        if self.ltime < min_ltime:
            with (locked(self.rlock),
                  self.zk_context as ctx):
                self.cache.refresh(ctx)

        protected_branches = None
        try:
            protected_branches = self.cache.protected[project_name]
        except KeyError:
            if exclude_unprotected:
                if default is RAISE_EXCEPTION:
                    raise LookupError(
                        f"No branches for project {project_name}")
                else:
                    return default

        if not exclude_unprotected:
            try:
                remainder_branches = self.cache.remainder[project_name]
            except KeyError:
                if default is RAISE_EXCEPTION:
                    raise LookupError(
                        f"No branches for project {project_name}")
                else:
                    return default

            if remainder_branches is not None:
                return (protected_branches or []) + remainder_branches

        return protected_branches

    def setProjectBranches(self, project_name, exclude_unprotected, branches):
        """Set the branch names for the given project.

        Use None as a sentinel value for the branches to indicate that
        there was a fetch error.

        :param str project_name:
            The project for the branches.
        :param bool exclude_unprotected:
            Whether this is a list of all or only protected branches.
        :param list[str] branches:
            The list of branches or None to indicate a fetch error.
        """

        with (locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):
            if exclude_unprotected:
                self.cache.protected[project_name] = branches
                remainder_branches = self.cache.remainder.get(project_name)
                if remainder_branches and branches:
                    remainder = list(set(remainder_branches) -
                                     set(branches))
                    self.cache.remainder[project_name] = remainder
            else:
                protected_branches = self.cache.protected.get(project_name)
                if protected_branches and branches:
                    remainder = list(set(branches) -
                                     set(protected_branches))
                else:
                    remainder = branches
                self.cache.remainder[project_name] = remainder

    def setProtected(self, project_name, branch, protected):
        """Correct the protection state of a branch.

        This may be called if a branch has changed state without us
        receiving an explicit event.
        """

        with (locked(self.wlock),
              self.zk_context as ctx,
              self.cache.activeContext(ctx)):
            protected_branches = self.cache.protected.get(project_name)
            remainder_branches = self.cache.remainder.get(project_name)
            if protected:
                if protected_branches is None:
                    # We've never run a protected query, so we
                    # should ignore this branch.
                    return
                else:
                    # We have run a protected query; if we have
                    # also run an unprotected query, we need to
                    # move the branch from remainder to protected.
                    if remainder_branches and branch in remainder_branches:
                        remainder_branches.remove(branch)
                    if branch not in protected_branches:
                        protected_branches.append(branch)
            else:
                if protected_branches and branch in protected_branches:
                    protected_branches.remove(branch)
                if remainder_branches is None:
                    # We've never run an unprotected query, so we
                    # should ignore this branch.
                    return
                else:
                    if branch not in remainder_branches:
                        remainder_branches.append(branch)

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
            with locked(self.rlock):
                self.cache.refresh(self.zk_context)

        merge_modes = None
        try:
            merge_modes = self.cache.merge_modes[project_name]
        except KeyError:
            if default is RAISE_EXCEPTION:
                raise LookupError(
                    f"No merge modes for project {project_name}")
            else:
                return default

        return merge_modes

    def setProjectMergeModes(self, project_name, merge_modes):
        """Set the supported merge modes for the given project.

        Use None as a sentinel value for the merge modes to indicate
        that there was a fetch error.

        :param str project_name:
            The project for the merge modes.
        :param list[int] merge_modes:
            The list of merge modes (by model ID) or None.

        """

        with locked(self.wlock):
            with self.cache.activeContext(self.zk_context):
                self.cache.merge_modes[project_name] = merge_modes

    @property
    def ltime(self):
        return self.cache._zstat.last_modified_transaction_id
