# Copyright 2020 BMW Group
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

import logging
from typing import Optional, Tuple, Dict, Any

from zuul.model import Tenant
from zuul.zk import ZooKeeperClient, ZooKeeperBase


class ZooKeeperUnparsedBranchConfig(ZooKeeperBase):
    CONFIG_ROOT = "/zuul/config"
    LAYOUT_ROOT = "/zuul/layout"
    LAYOUT_VERSION_ROOT = "%s/version" % LAYOUT_ROOT

    log = logging.getLogger(
        "zuul.zk.unparsed_branch_config.ZooKeeperUnparsedBranchConfig")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)
        self._layout_versions: Dict[str, int] = {}

    def isLoaded(self, tenant: Tenant):
        return tenant.name in self._layout_versions

    def getVersion(self, tenant: Tenant) -> Optional[int]:
        """
        Get tenant's layout version.

        A layout version is a hash over all relevant files for the given
        tenant.

        :param tenant: Tenant
        :return: Tenant's layout relevant files hash
        """
        with self.kazoo_client.ReadLock(self.LAYOUT_ROOT):
            version_path = "%s/%s" % (self.LAYOUT_VERSION_ROOT, tenant.name)
            version = None
            if self.kazoo_client.exists(version_path):
                data, _ = self.kazoo_client.get(version_path)
                version = int(data.decode(encoding='UTF-8')) if data else None

            self.log.debug("Getting layout version for %s (%s): %s",
                           tenant.name, version_path, version)
            return version

    def setVersion(self, tenant: Tenant, scheduler_name: str,
                   version: Optional[int] = None) -> None:
        with self.kazoo_client.WriteLock(self.LAYOUT_VERSION_ROOT):
            version_path = "%s/%s" % (self.LAYOUT_VERSION_ROOT, tenant.name)
            version_data, version_stat = self.kazoo_client.get(version_path)\
                if self.kazoo_client.exists(version_path) else (None, None)
            next_version = version or 1
            if version_stat is None:
                self.kazoo_client.create(
                    version_path, str(next_version).encode(encoding='UTF-8'),
                    makepath=True)
            else:
                current_version = int(version_data.decode(encoding='UTF-8'))
                next_version = version or (current_version + 1)
                if next_version > current_version:
                    self.kazoo_client.set(
                        version_path,
                        str(next_version).encode(encoding='UTF-8'),
                        version=version_stat.version)
                elif next_version < current_version:
                    raise Exception("Trying to update version %s with %s" % (
                        current_version, next_version))

            self.setLocalVersion(tenant, scheduler_name, next_version)

            self.log.debug("Setting layout version for %s (%s): %s",
                           tenant.name, version_path, next_version)

    def setLocalVersion(self, tenant: Tenant, scheduler_name: str,
                        version: int) -> None:
        version_path = "%s/%s" % (self.LAYOUT_VERSION_ROOT, tenant.name)
        scheduler_path = "%s/%s" % (version_path, scheduler_name)
        scheduler_stat = self.kazoo_client.exists(scheduler_path)
        if scheduler_stat is None:
            self.kazoo_client.create(
                scheduler_path, str(version).encode(encoding='UTF-8'),
                makepath=True, ephemeral=True)
        else:
            self.kazoo_client.set(
                scheduler_path, str(version).encode(encoding='UTF-8'),
                version=scheduler_stat.version)

        self._layout_versions[tenant.name] = version

    def checkNewVersion(self, tenant: Tenant) -> Optional[int]:
        """
        Compares the version of the tenant with ZooKeeper and returns None if
        they match or the one stored in Zookeeper if they dont match.

        :param tenant: Tenant to check.
        :return: Newer version from zookeeper if check fails.
        """
        tenant_layout_version = self._layout_versions.get(tenant.name)
        version_path = "%s/%s" % (self.LAYOUT_VERSION_ROOT, tenant.name)
        with self.kazoo_client.ReadLock(self.LAYOUT_VERSION_ROOT):
            version_data, version_stat = self.kazoo_client.get(version_path)\
                if self.kazoo_client.exists(version_path) else (None, None)
            if version_stat:
                zk_version = int(version_data.decode(encoding='UTF-8'))
                self.log.debug(
                    "Checking layout version for %s (%s): %s <> %s",
                    tenant.name, version_path, tenant_layout_version,
                    zk_version)
                return zk_version if zk_version != tenant_layout_version\
                    else None
            self.log.debug("Checking layout version for %s (%s):"
                           " %s <> No ZK version", tenant.name,
                           version_path, tenant_layout_version)
            return None

    def peersCount(self, tenant: Tenant) -> int:
        version_path = "%s/%s" % (self.LAYOUT_VERSION_ROOT, tenant.name)
        return len(self.kazoo_client.get_children(version_path))

    def tenantLock(self, tenant: str):
        return self.kazoo_client.Lock("%s/%s" % (self.CONFIG_ROOT, tenant))

    def load(self, tenant: str, project: str, branch: str, path: str)\
            -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Load unparsed config from zookeeper under
        /zuul/config/<tenant>/<project>/<branch>/<path-to-config>/<shard>

        :param tenant: Tenant name
        :param project: Project name
        :param branch: Branch
        :param path: Path
        :return: The unparsed config an its version as a tuple or None.
        """
        lock = self.kazoo_client.ReadLock(self.CONFIG_ROOT)
        with self.client.withLock(lock):
            node = "%s/%s/%s/%s/%s" % (
                self.CONFIG_ROOT, tenant, project, branch,
                path.replace("/", "_"))
            self.log.debug("Loading unparsed branch config from %s", node)
            return self.client.loadShardedContent(
                node, including_metadata=True)

    def save(self, tenant: str, project: str, branch: str, path: str,
             data: Optional[str]) -> None:
        """
        Saves unparsed configuration to zookeeper under
        /zuul/config/<tenant>/<project>/<branch>/<path-to-config>/<shard>

        An update only happens if the currently stored content differs from
        the provided in `data` param.

        This operation needs to be explicitly locked using lock from
        `getConfigWriteLock`

        :param tenant: Tenant name
        :param project: Project name
        :param branch: Branch
        :param path: Path
        :param data: Unparsed configuration yaml
        """

        lock = self.kazoo_client.WriteLock(self.CONFIG_ROOT)
        with self.client.withLock(lock):
            node = "%s/%s/%s/%s/%s" % (
                self.CONFIG_ROOT, tenant, project, branch,
                path.replace("/", "_"))

            self.log.debug("Saving unparsed branch config to %s", node)
            return self.client.saveShardedContent(node, data, metadata=dict(
                tenant=tenant,
                project=project,
                branch=branch,
                path=path,
            ))
