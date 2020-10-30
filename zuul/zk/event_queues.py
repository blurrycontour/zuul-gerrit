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
from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Generator,
    TypeVar,
    Tuple,
    Type,
)

from kazoo.exceptions import NoNodeError

from zuul import model
from zuul.lib.connections import ConnectionRegistry
from zuul.zk import ZooKeeperClient, ZooKeeperBase


RESULT_EVENT_TYPE_MAP: Dict[str, Type[model.ResultEvent]] = {
    "BuildCompletedEvent": model.BuildCompletedEvent,
    "BuildPausedEvent": model.BuildPausedEvent,
    "BuildStartedEvent": model.BuildStartedEvent,
    "FilesChangesCompletedEvent": model.FilesChangesCompletedEvent,
    "MergeCompletedEvent": model.MergeCompletedEvent,
    "NodesProvisionedEvent": model.NodesProvisionedEvent,
}

MANAGEMENT_EVENT_TYPE_MAP: Dict[str, Type[model.ManagementEvent]] = {
    "DequeueEvent": model.DequeueEvent,
    "EnqueueEvent": model.EnqueueEvent,
    "PromoteEvent": model.PromoteEvent,
    "ReconfigureEvent": model.ReconfigureEvent,
    "SmartReconfigureEvent": model.SmartReconfigureEvent,
    "TenantReconfigureEvent": model.TenantReconfigureEvent,
}

_AbstractEventT = TypeVar("_AbstractEventT", bound=model.AbstractEvent)


class ZooKeeperEventQueue(Generic[_AbstractEventT], ZooKeeperBase, Iterable):
    """Abstract API for tenant specific events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.ZooKeeperEventQueue")

    TENANT_ROOT = "/zuul/events/tenant"
    event_root: str

    def __len__(self) -> int:
        stat = self.kazoo_client.exists(self.event_root)
        return stat.children_count if stat else 0

    def hasEvents(self) -> bool:
        return bool(len(self))

    def ack(self, event: _AbstractEventT) -> None:
        try:
            self.kazoo_client.delete(event.ack_id, recursive=True)
        except NoNodeError:
            self.log.warning("Event %s was already acknowledged", event)

    def _put(self, data: Dict[str, Any]) -> str:
        return self.kazoo_client.create(
            self.event_root,
            json.dumps(data).encode("utf-8"),
            sequence=True,
            makepath=True,
        )

    def _iter_events(
        self,
    ) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        try:
            events = self.kazoo_client.get_children(self.event_root)
        except NoNodeError:
            return

        # We need to sort this ourself, since Kazoo doesn't guarantee any
        # ordering of the returned children.
        for event_id in sorted(events):
            path = self.event_root + event_id
            # TODO: implement sharding of large events
            data, _ = self.kazoo_client.get(path)
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                self.log.exception("Malformed event data in %s", path)
                self._remove(path)
                continue
            yield path, event

    def _remove(self, path: str) -> None:
        with suppress(NoNodeError):
            self.kazoo_client.delete(path, recursive=True)


class ZooKeeperEventQueueRegistry(defaultdict):
    def __init__(self, queue_factory: Callable[[str], ZooKeeperEventQueue]):
        self.queue_factory = queue_factory

    def __missing__(self, key: str) -> ZooKeeperEventQueue:
        return self.queue_factory(key)


class ZooKeeperManagementEventQueue(
    ZooKeeperEventQueue[model.ManagementEvent]
):
    """Management events via ZooKeeper"""

    log = logging.getLogger(
        "zuul.zk.event_queues.ZooKeeperManagementEventQueue"
    )

    def __init__(self, client: ZooKeeperClient, tenant_name: str):
        self.event_root = "{}/{}/management/".format(
            self.TENANT_ROOT, tenant_name
        )
        super().__init__(client)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient
    ) -> Dict[str, "ZooKeeperManagementEventQueue"]:
        return ZooKeeperEventQueueRegistry(lambda t: cls(client, t))

    def put(self, event: model.ManagementEvent) -> None:
        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
        }
        event.ack_id = self._put(data)

    def __iter__(self) -> Generator[model.ManagementEvent, None, None]:
        for path, data in self._iter_events():
            try:
                event_class = MANAGEMENT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_id = path
            yield event


class ZooKeeperResultEventQueue(ZooKeeperEventQueue[model.ResultEvent]):
    """Result events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.ZooKeeperResultEventQueue")

    def __init__(self, client: ZooKeeperClient, tenant_name: str):
        self.event_root = "{}/{}/results/".format(
            self.TENANT_ROOT, tenant_name
        )
        super().__init__(client)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient
    ) -> Dict[str, "ZooKeeperResultEventQueue"]:
        return ZooKeeperEventQueueRegistry(lambda t: cls(client, t))

    def put(self, event: model.ResultEvent) -> None:
        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
        }
        event.ack_id = self._put(data)

    def __iter__(self) -> Generator[model.ResultEvent, None, None]:
        for path, data in self._iter_events():
            try:
                event_class = RESULT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_id = path
            yield event


class ZooKeeperTriggerEventQueue(ZooKeeperEventQueue[model.TriggerEvent]):
    """Trigger events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.ZooKeeperTriggerEventQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        tenant_name: str,
        connections: ConnectionRegistry,
    ):
        self.event_root = "{}/{}/triggers/".format(
            self.TENANT_ROOT, tenant_name
        )
        self.connections = connections
        super().__init__(client)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient, connections: ConnectionRegistry
    ) -> Dict[str, "ZooKeeperTriggerEventQueue"]:
        return ZooKeeperEventQueueRegistry(
            lambda t: cls(client, t, connections)
        )

    def put(self, driver_name: str, event: model.TriggerEvent) -> None:
        data = {
            "driver_name": driver_name,
            "event_data": event.toDict(),
        }
        event.ack_id = self._put(data)

    def __iter__(self) -> Generator[model.TriggerEvent, None, None]:
        for path, data in self._iter_events():
            try:
                event_class = self.connections.getTriggerEventClass(
                    data["driver_name"]
                )
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_id = path
            yield event
