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
import uuid
from collections import defaultdict, namedtuple
from collections.abc import Iterable
from contextlib import suppress
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Generator,
    List,
    Optional,
    Set,
    TypeVar,
    Tuple,
    Type,
)

from kazoo.exceptions import NoNodeError
from kazoo.protocol.states import EventType, WatchedEvent, ZnodeStat

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

EventAckRef = namedtuple("EventAckRef", ("path", "version"))

UNKNOWN_ZVERSION = -1


class ZooKeeperEventWatcher(ZooKeeperBase):

    log = logging.getLogger("zuul.zk.event_queues.ZooKeeperEventWatcher")

    TENANT_ROOT = "/zuul/events/tenant"
    QUEUES = (
        "management",
        "results",
        "triggers",
    )

    def __init__(self, client: ZooKeeperClient, callback: Callable[[], Any]):
        super().__init__(client)
        self.callback: Callable[[], Any] = callback
        self.watched_queues: Set[str] = set()
        self.kazoo_client.ensure_path(self.TENANT_ROOT)
        self.kazoo_client.ChildrenWatch(self.TENANT_ROOT, self._tenantWatch)

    def _tenantWatch(
        self,
        tenants: List[str],
    ) -> None:
        for tenant_name in tenants:
            for queue_name in self.QUEUES:
                queue_path = "/".join(
                    (self.TENANT_ROOT, tenant_name, queue_name)
                )
                if queue_path in self.watched_queues:
                    continue

                self.kazoo_client.ensure_path(queue_path)
                self.kazoo_client.ChildrenWatch(
                    queue_path,
                    self._queueWatch,
                    send_event=True,
                )
                self.watched_queues.add(queue_path)

    def _queueWatch(
        self,
        event_list: List[str],
        event: Optional[WatchedEvent] = None,
    ) -> None:
        if event is None:
            # Handle initial call when the watch is created. If there are
            # already events in the queue we trigger the callback.
            if event_list:
                self.callback()
        elif event.type == EventType.CHILD:
            self.callback()


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
        if not event.ack_ref:
            raise RuntimeError("Cannot ack event %s without reference", event)
        try:
            self.kazoo_client.delete(
                event.ack_ref.path,
                version=event.ack_ref.version,
                recursive=True,
            )
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
    ) -> Generator[Tuple[Dict[str, Any], EventAckRef], None, None]:
        try:
            events = self.kazoo_client.get_children(self.event_root)
        except NoNodeError:
            return

        # We need to sort this ourself, since Kazoo doesn't guarantee any
        # ordering of the returned children.
        for event_id in sorted(events):
            path = self.event_root + event_id
            # TODO: implement sharding of large events
            data, zstat = self.kazoo_client.get(path)
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                self.log.exception("Malformed event data in %s", path)
                self._remove(path)
                continue
            yield event, EventAckRef(path, zstat.version)

    def _remove(self, path: str) -> None:
        with suppress(NoNodeError):
            self.kazoo_client.delete(path, recursive=True)


class ZooKeeperEventQueueRegistry(defaultdict):
    def __init__(self, queue_factory: Callable[[str], ZooKeeperEventQueue]):
        self.queue_factory = queue_factory

    def __missing__(self, key: str) -> ZooKeeperEventQueue:
        queue = self.queue_factory(key)
        self[key] = queue
        return queue


class ManagementEventResultFuture(ZooKeeperBase):

    log = logging.getLogger("zuul.zk.event_queues.MangementEventResultFuture")

    def __init__(self, client: ZooKeeperClient, result_path: str):
        super().__init__(client)
        self._result_path = result_path
        self._wait_event = threading.Event()
        self.kazoo_client.DataWatch(self._result_path, self._result_callback)

    def _result_callback(
        self,
        data: Optional[bytes],
        stat: Optional[ZnodeStat],
        event: Optional[WatchedEvent],
    ) -> Optional[bool]:
        if data is None:
            # Igore events w/o any data
            return None
        self._wait_event.set()
        # Stop the watch if we got a result
        return False

    def wait(self, timeout: Optional[float] = None) -> bool:
        try:
            if not self._wait_event.wait(timeout):
                return False
            try:
                data, _ = self.kazoo_client.get(self._result_path)
                result = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                self.log.exception(
                    "Malformed result data in %s", self._result_path
                )
                raise
            tb = result.get("traceback")
            if tb is not None:
                # TODO: raise some kind of ManagementEventException here
                raise RuntimeError(tb)
        finally:
            with suppress(NoNodeError):
                self.kazoo_client.delete(self._result_path)
        return True


class ZooKeeperManagementEventQueue(
    ZooKeeperEventQueue[model.ManagementEvent]
):
    """Management events via ZooKeeper"""

    RESULTS_ROOT = "/zuul/results/management"

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

    def put(
        self, event: model.ManagementEvent, needs_result=True
    ) -> Optional[ManagementEventResultFuture]:
        result_path = None
        if needs_result:
            result_path = "/".join((self.RESULTS_ROOT, str(uuid.uuid4())))

        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
            "result_path": result_path,
        }
        event.ack_ref = EventAckRef(self._put(data), UNKNOWN_ZVERSION)
        if result_path is not None:
            return ManagementEventResultFuture(self.client, result_path)
        return None

    def __iter__(self) -> Generator[model.ManagementEvent, None, None]:
        event_list: List[model.ManagementEvent] = []
        for data, ack_ref in self._iter_events():
            try:
                event_class = MANAGEMENT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
                result_path = data["result_path"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            event.result_ref = result_path

            with suppress(ValueError):
                other_event = event_list[event_list.index(event)]
                if isinstance(other_event, model.TenantReconfigureEvent):
                    other_event.merge(event)
                    continue
            event_list.append(event)
        yield from event_list

    def ack(self, event: model.ManagementEvent) -> None:
        self._ack(event, event.traceback)
        if isinstance(event, model.TenantReconfigureEvent):
            for merged_event in event.merged_events:
                self._ack(merged_event, event.traceback)

    def _ack(
        self, event: model.ManagementEvent, event_tb: Optional[str]
    ) -> None:
        if not event.ack_ref:
            raise RuntimeError("Cannot ack event %s without reference", event)
        try:
            self.kazoo_client.delete(
                event.ack_ref.path,
                version=event.ack_ref.version,
                recursive=True,
            )
        except NoNodeError:
            self.log.warning("Event %s was already acknowledged", event)
            return

        if not event.result_ref:
            return

        result_data = {"traceback": event_tb}
        self.kazoo_client.create(
            event.result_ref,
            json.dumps(result_data).encode("utf-8"),
            ephemeral=True,
            makepath=True,
        )


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
        event.ack_ref = EventAckRef(self._put(data), UNKNOWN_ZVERSION)

    def __iter__(self) -> Generator[model.ResultEvent, None, None]:
        for data, ack_ref in self._iter_events():
            try:
                event_class = RESULT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
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
        event.ack_ref = EventAckRef(self._put(data), UNKNOWN_ZVERSION)

    def __iter__(self) -> Generator[model.TriggerEvent, None, None]:
        for data, ack_ref in self._iter_events():
            try:
                event_class = self.connections.getTriggerEventClass(
                    data["driver_name"]
                )
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            yield event
