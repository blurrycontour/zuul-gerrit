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

import enum
import json
import logging
import threading
import uuid
from collections import namedtuple
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
from zuul.lib.collections import DefaultKeyDict
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

TENANT_ROOT = "/zuul/events/tenant"
SCHEDULER_GLOBAL_ROOT = "/zuul/events/scheduler-global"

_AbstractEventT = TypeVar("_AbstractEventT", bound=model.AbstractEvent)
_EventQueueT = TypeVar("_EventQueueT", bound="ZooKeeperEventQueue")

EventAckRef = namedtuple("EventAckRef", ("path", "version"))

UNKNOWN_ZVERSION = -1


class EventPrefix(enum.Enum):
    MANAGEMENT = "100"
    RESULT = "200"
    TRIGGER = "300"


class GlobalEventWatcher(ZooKeeperBase):

    log = logging.getLogger("zuul.zk.event_queues.EventQueueWatcher")

    def __init__(self, client: ZooKeeperClient, callback: Callable[[], Any]):
        super().__init__(client)
        self.callback: Callable[[], Any] = callback
        self.kazoo_client.ensure_path(SCHEDULER_GLOBAL_ROOT)
        self.kazoo_client.ChildrenWatch(
            SCHEDULER_GLOBAL_ROOT, self._event_watch
        )

    def _event_watch(
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


class PipelineEventWatcher(ZooKeeperBase):

    log = logging.getLogger("zuul.zk.event_queues.EventQueueWatcher")

    def __init__(self, client: ZooKeeperClient, callback: Callable[[], Any]):
        super().__init__(client)
        self.callback: Callable[[], Any] = callback
        self.watched_tenants: Set[str] = set()
        self.watched_pipelines: Set[str] = set()
        self.kazoo_client.ensure_path(TENANT_ROOT)
        self.kazoo_client.ChildrenWatch(TENANT_ROOT, self._tenant_watch)

    def _tenant_watch(
        self,
        tenants: List[str],
    ) -> None:
        for tenant_name in tenants:
            tenant_path = "/".join((TENANT_ROOT, tenant_name))

            if tenant_path in self.watched_tenants:
                continue

            self.kazoo_client.ChildrenWatch(
                tenant_path,
                lambda p: self._pipeline_watch(tenant_name, p),
            )
            self.watched_tenants.add(tenant_path)

    def _pipeline_watch(
        self,
        tenant_name: str,
        pipelines: List[str],
    ) -> None:
        for pipeline_name in pipelines:
            pipeline_path = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
            if pipeline_path in self.watched_pipelines:
                continue

            self.kazoo_client.ChildrenWatch(
                pipeline_path,
                self._event_watch,
                send_event=True,
            )
            self.watched_pipelines.add(pipeline_path)

    def _event_watch(
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

    def __init__(
        self,
        client: ZooKeeperClient,
        event_root: str,
        event_prefix: EventPrefix,
    ):
        super().__init__(client)
        self.event_prefix = event_prefix
        self.event_root = event_root
        self.kazoo_client.ensure_path(self.event_root)

    def __len__(self) -> int:
        try:
            return len(
                [
                    e
                    for e in self.kazoo_client.get_children(self.event_root)
                    if e.startswith(self.event_prefix.value)
                ]
            )
        except NoNodeError:
            return 0

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
        event_path = "{}/{}-".format(self.event_root, self.event_prefix.value)
        return self.kazoo_client.create(
            event_path,
            json.dumps(data).encode("utf-8"),
            sequence=True,
            makepath=True,
        )

    def _iter_events(
        self,
    ) -> Generator[Tuple[Dict[str, Any], ZnodeStat, EventAckRef], None, None]:
        try:
            events = self.kazoo_client.get_children(self.event_root)
        except NoNodeError:
            return

        # We need to sort this ourself, since Kazoo doesn't guarantee any
        # ordering of the returned children.
        events = sorted(
            e for e in events if e.startswith(self.event_prefix.value)
        )
        for event_id in events:
            path = "/".join((self.event_root, event_id))
            # TODO: implement sharding of large events
            data, zstat = self.kazoo_client.get(path)
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                self.log.exception("Malformed event data in %s", path)
                self._remove(path)
                continue
            yield event, zstat, EventAckRef(path, zstat.version)

    def _remove(self, path: str) -> None:
        with suppress(NoNodeError):
            self.kazoo_client.delete(path, recursive=True)


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


class ManagementEventQueue(ZooKeeperEventQueue[model.ManagementEvent]):
    """Management events via ZooKeeper"""

    RESULTS_ROOT = "/zuul/results/management"

    log = logging.getLogger("zuul.zk.event_queues.ManagementEventQueue")

    def put(
        self, event: model.ManagementEvent, needs_result=True
    ) -> Optional[ManagementEventResultFuture]:
        result_path = None
        # If this event is forwarded it might have a result ref that
        # we need to forward.
        if event.result_ref:
            result_path = event.result_ref
        elif needs_result:
            result_path = "/".join((self.RESULTS_ROOT, str(uuid.uuid4())))

        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
            "result_path": result_path,
        }
        self._put(data)
        if needs_result and result_path:
            return ManagementEventResultFuture(self.client, result_path)
        return None

    def __iter__(self) -> Generator[model.ManagementEvent, None, None]:
        event_list: List[model.ManagementEvent] = []
        for data, zstat, ack_ref in self._iter_events():
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
            event.zuul_cache_ltime = event.zuul_cache_ltime or zstat.czxid

            with suppress(ValueError):
                other_event = event_list[event_list.index(event)]
                if isinstance(other_event, model.TenantReconfigureEvent):
                    other_event.merge(event)
                    continue
            event_list.append(event)
        yield from event_list

    def ack(self, event: model.ManagementEvent) -> None:
        super().ack(event)
        self._report_result(event)
        if isinstance(event, model.TenantReconfigureEvent):
            for merged_event in event.merged_events:
                super().ack(merged_event)
                merged_event.traceback = event.traceback
                self._report_result(merged_event)

    def _report_result(self, event: model.ManagementEvent) -> None:
        if not event.result_ref:
            return

        result_data = {"traceback": event.traceback}
        self.kazoo_client.create(
            event.result_ref,
            json.dumps(result_data).encode("utf-8"),
            ephemeral=True,
            makepath=True,
        )


class PipelineManagementEventQueue(ManagementEventQueue):
    log = logging.getLogger(
        "zuul.zk.event_queues.PipelineManagementEventQueue"
    )

    def __init__(
        self, client: ZooKeeperClient, tenant_name: str, pipeline_name: str
    ):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, EventPrefix.MANAGEMENT)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient
    ) -> DefaultKeyDict[DefaultKeyDict["PipelineManagementEventQueue"]]:
        return DefaultKeyDict(lambda t: cls._create_registry(client, t))

    @classmethod
    def _create_registry(
        cls, client: ZooKeeperClient, tenant_name: str
    ) -> DefaultKeyDict["PipelineManagementEventQueue"]:
        return DefaultKeyDict(lambda p: cls(client, tenant_name, p))


class GlobalManagementEventQueue(ManagementEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.GlobalManagementEventQueue")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client, SCHEDULER_GLOBAL_ROOT, EventPrefix.MANAGEMENT)

    def ack_without_result(self, event: model.ManagementEvent) -> None:
        super(ManagementEventQueue, self).ack(event)
        if isinstance(event, model.TenantReconfigureEvent):
            for merged_event in event.merged_events:
                super(ManagementEventQueue, self).ack(merged_event)


class PipelineResultEventQueue(ZooKeeperEventQueue[model.ResultEvent]):
    """Result events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.PipelineResultEventQueue")

    def __init__(
        self, client: ZooKeeperClient, tenant_name: str, pipeline_name: str
    ):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, EventPrefix.RESULT)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient
    ) -> DefaultKeyDict[DefaultKeyDict["PipelineResultEventQueue"]]:
        return DefaultKeyDict(lambda t: cls._create_registry(client, t))

    @classmethod
    def _create_registry(
        cls, client: ZooKeeperClient, tenant_name: str
    ) -> DefaultKeyDict["PipelineResultEventQueue"]:
        return DefaultKeyDict(lambda p: cls(client, tenant_name, p))

    def put(self, event: model.ResultEvent) -> None:
        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
        }
        self._put(data)

    def __iter__(self) -> Generator[model.ResultEvent, None, None]:
        for data, zstat, ack_ref in self._iter_events():
            try:
                event_class = RESULT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            event.zuul_cache_ltime = event.zuul_cache_ltime or zstat.czxid
            yield event


class TriggerEventQueue(ZooKeeperEventQueue[model.TriggerEvent]):
    """Trigger events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.TriggerEventQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        event_root: str,
        connections: ConnectionRegistry,
    ):
        self.connections = connections
        super().__init__(client, event_root, EventPrefix.TRIGGER)

    def put(self, driver_name: str, event: model.TriggerEvent) -> None:
        data = {
            "driver_name": driver_name,
            "event_data": event.toDict(),
        }
        self._put(data)

    def __iter__(self) -> Generator[model.TriggerEvent, None, None]:
        for data, zstat, ack_ref in self._iter_events():
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
            event.driver_name = data["driver_name"]
            event.zuul_cache_ltime = event.zuul_cache_ltime or zstat.czxid
            yield event


class GlobalTriggerEventQueue(TriggerEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.GlobalTriggerEventQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        connections: ConnectionRegistry,
    ):
        super().__init__(client, SCHEDULER_GLOBAL_ROOT, connections)


class PipelineTriggerEventQueue(TriggerEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.PipelineTriggerEventQueue")

    def __init__(
        self,
        client: ZooKeeperClient,
        tenant_name: str,
        pipeline_name: str,
        connections: ConnectionRegistry,
    ):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, connections)

    @classmethod
    def create_registry(
        cls, client: ZooKeeperClient, connections: ConnectionRegistry
    ) -> DefaultKeyDict[DefaultKeyDict["TriggerEventQueue"]]:
        return DefaultKeyDict(
            lambda t: cls._create_registry(client, t, connections)
        )

    @classmethod
    def _create_registry(
        cls,
        client: ZooKeeperClient,
        tenant_name: str,
        connections: ConnectionRegistry,
    ) -> DefaultKeyDict["TriggerEventQueue"]:
        return DefaultKeyDict(
            lambda p: cls(client, tenant_name, p, connections)
        )
