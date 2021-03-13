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
import json
import logging
import threading
from typing import Any, Dict, List, Optional

from kazoo.client import KazooClient

from zuul.zk import NoClientException, ZooKeeperBase, ZooKeeperClient


class ZooKeeperComponentReadOnly(object):
    """
    Read-only component object.
    """

    STOPPED = 'stopped'
    RUNNING = 'running'
    PAUSED = 'paused'

    def __init__(self, client: ZooKeeperClient, content: Dict[str, Any]):
        self._client = client
        self._content = content

    @property
    def kazoo_client(self) -> KazooClient:
        if not self._client.client:
            raise NoClientException()
        return self._client.client

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Gets an attribute of the component.

        :param key: Attribute key
        :param default: Default value (default: None)
        :return: Value of the attribute
        """
        return self._content.get(key, default)


class ZooKeeperComponent(ZooKeeperComponentReadOnly):
    """
    Read/write component object.

    This object holds an offline cache of all the component's attributes.
    In case of an failed update to zookeeper the local cache will still
    hold the fresh values. Updating any attribute uploads all attributes to
    zookeeper.

    This enables this object to be used as a local key/value store even if
    zookeeper connection got lost. One must still catch exceptions related
    to zookeeper connection loss.
    """

    log = logging.getLogger("zuul.zk.components.ZooKeeperComponent")

    def __init__(
        self,
        client: ZooKeeperClient,
        kind: str,
        hostname: str,
        content: Dict[str, Any],
    ):
        super().__init__(client, content)
        self._kind = kind
        self._persisted = False
        self._hostname = hostname
        self._path = self._register(content)
        self._set_lock = threading.Lock()

    def set(self, key: str, value: int) -> None:
        """
        Sets an attribute of a component and uploads the whole component state
        to zookeeper.

        Upload only happens if the new value changed or if an previous upload
        failed.

        :param key: Attribute key
        :param value: Value
        """

        with self._set_lock:
            upload = self._content.get(key) != value or not self._persisted
            self._content[key] = value
            if upload:
                self._persisted = False
                stat = self.kazoo_client.exists(self._path)
                if not stat:  # Re-register, if connection to zk was lost
                    self._path = self._register(self._content)
                else:
                    content = json.dumps(self._content).encode(
                        encoding="UTF-8"
                    )
                    self.kazoo_client.set(
                        self._path, content, version=stat.version
                    )
                self._persisted = True

    def _register(self, content: Dict[str, Any]) -> str:
        path = "{}/{}/{}-".format(
            ZooKeeperComponentRegistry.ROOT, self._kind, self._hostname
        )
        self.log.debug(f"Creating {path} in Zookeeper")
        return self.kazoo_client.create(
            path,
            json.dumps(content).encode("utf-8"),
            makepath=True,
            ephemeral=True,
            sequence=True,
        )

    def unregister(self):
        self.kazoo_client.delete(self._path)


class ZooKeeperComponentRegistry(ZooKeeperBase):
    """
    ZooKeeper component registry. Each zuul component can register itself
    using this registry. This will create a ephemeral zookeeper node, which
    will be then deleted in case such component looses connection to zookeeper.

    Any other component may request a list of registered components to check
    their properties. List of components received by other components are
    read-only. Only the component itself can update its entry in the registry.
    """

    ROOT = "/zuul/components"

    log = logging.getLogger("zuul.zk.components.ZooKeeperComponentRegistry")

    def all(self, kind: str) -> List[ZooKeeperComponentReadOnly]:
        """
        Get all registered components of a given kind. Components obtained
        using this method cannot be updated.

        :param kind: Kind of components
        :return: List of read-only components
        """

        result = []
        path = "{}/{}".format(self.ROOT, kind)
        self.kazoo_client.ensure_path(path)
        for node in self.kazoo_client.get_children(path):
            path = "{}/{}/{}".format(self.ROOT, kind, node)
            data, _ = self.kazoo_client.get(path)
            content = json.loads(data.decode("UTF-8"))
            result.append(ZooKeeperComponentReadOnly(self.client, content))
        return result

    def register(self, kind: str, hostname: str) -> ZooKeeperComponent:
        """
        Register component with a hostname. This method returns an updateable
        component object.

        :param kind: Kind of component
        :param hostname: Hostname
        :return: Path representing the components's ZNode
        """
        return ZooKeeperComponent(
            self.client,
            kind,
            hostname,
            dict(
                hostname=hostname,
                state=ZooKeeperComponent.STOPPED,
            ),
        )
