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
import functools
import json
import logging
import threading
import time
import uuid
from collections import namedtuple
from collections.abc import Iterable
from contextlib import suppress

from kazoo.exceptions import NoNodeError
from kazoo.protocol.states import EventType
from kazoo.recipe.election import Election

from zuul import model
from zuul.lib.collections import DefaultKeyDict
from zuul.zk import ZooKeeperSimpleBase

RESULT_EVENT_TYPE_MAP = {
    "BuildCompletedEvent": model.BuildCompletedEvent,
    "BuildPausedEvent": model.BuildPausedEvent,
    "BuildStartedEvent": model.BuildStartedEvent,
    "BuildStatusEvent": model.BuildStatusEvent,
    "FilesChangesCompletedEvent": model.FilesChangesCompletedEvent,
    "MergeCompletedEvent": model.MergeCompletedEvent,
    "NodesProvisionedEvent": model.NodesProvisionedEvent,
}

MANAGEMENT_EVENT_TYPE_MAP = {
    "DequeueEvent": model.DequeueEvent,
    "EnqueueEvent": model.EnqueueEvent,
    "PromoteEvent": model.PromoteEvent,
    "ReconfigureEvent": model.ReconfigureEvent,
    "SmartReconfigureEvent": model.SmartReconfigureEvent,
    "TenantReconfigureEvent": model.TenantReconfigureEvent,
}

TENANT_ROOT = "/zuul/events/tenant"
SCHEDULER_GLOBAL_ROOT = "/zuul/events/scheduler-global"
CONNECTION_ROOT = "/zuul/events/connection"

# This is the path to the serialized from of the event in ZK (along
# with the version when it was read (which should not change since
# events are immutable in queue)).  When processing of the event is
# complete, this is the path that should be deleted in order to
# acknowledge it and prevent re-processing.  Instances of this are
# dynamically created and attached to de-serialized Event instances.
EventAckRef = namedtuple("EventAckRef", ("path", "version"))

UNKNOWN_ZVERSION = -1


class EventPrefix(enum.Enum):
    MANAGEMENT = "100"
    RESULT = "200"
    TRIGGER = "300"


class GlobalEventWatcher(ZooKeeperSimpleBase):

    log = logging.getLogger("zuul.zk.event_queues.EventQueueWatcher")

    def __init__(self, client, callback):
        super().__init__(client)
        self.callback = callback
        self.kazoo_client.ensure_path(SCHEDULER_GLOBAL_ROOT)
        self.kazoo_client.ChildrenWatch(
            SCHEDULER_GLOBAL_ROOT, self._eventWatch
        )

    def _eventWatch(self, event_list):
        if event_list:
            self.callback()


class PipelineEventWatcher(ZooKeeperSimpleBase):

    log = logging.getLogger("zuul.zk.event_queues.EventQueueWatcher")

    def __init__(self, client, callback):
        super().__init__(client)
        self.callback = callback
        self.watched_tenants = set()
        self.watched_pipelines = set()
        self.kazoo_client.ensure_path(TENANT_ROOT)
        self.kazoo_client.ChildrenWatch(TENANT_ROOT, self._tenantWatch)

    def _tenantWatch(self, tenants):
        for tenant_name in tenants:
            tenant_path = "/".join((TENANT_ROOT, tenant_name))

            if tenant_path in self.watched_tenants:
                continue

            self.kazoo_client.ChildrenWatch(
                tenant_path,
                lambda p: self._pipelineWatch(tenant_name, p),
            )
            self.watched_tenants.add(tenant_path)

    def _pipelineWatch(self, tenant_name, pipelines):
        for pipeline_name in pipelines:
            pipeline_path = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
            if pipeline_path in self.watched_pipelines:
                continue

            self.kazoo_client.ChildrenWatch(
                pipeline_path,
                self._eventWatch,
                send_event=True,
            )
            self.watched_pipelines.add(pipeline_path)

    def _eventWatch(self, event_list, event=None):
        if event is None:
            # Handle initial call when the watch is created. If there are
            # already events in the queue we trigger the callback.
            if event_list:
                self.callback()
        elif event.type == EventType.CHILD:
            self.callback()


class ZooKeeperEventQueue(ZooKeeperSimpleBase, Iterable):
    """Abstract API for events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.ZooKeeperEventQueue")

    def __init__(self, client, event_root):
        super().__init__(client)
        self.event_root = event_root
        self.kazoo_client.ensure_path(self.event_root)

    def _listEvents(self):
        return self.kazoo_client.get_children(self.event_root)

    def __len__(self):
        try:
            return len(self._listEvents())
        except NoNodeError:
            return 0

    def hasEvents(self):
        return bool(len(self))

    def ack(self, event):
        # Event.ack_ref is an EventAckRef, previously attached to an
        # event object when it was de-serialized.
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

    @property
    def _event_create_path(self):
        return f"{self.event_root}/"

    def _put(self, data):
        return self.kazoo_client.create(
            self._event_create_path,
            json.dumps(data).encode("utf-8"),
            sequence=True,
            makepath=True,
        )

    def _iterEvents(self):
        try:
            # We need to sort this ourself, since Kazoo doesn't guarantee any
            # ordering of the returned children.
            events = sorted(self._listEvents())
        except NoNodeError:
            return

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
            yield event, EventAckRef(path, zstat.version), zstat

    def _remove(self, path, version=UNKNOWN_ZVERSION):
        with suppress(NoNodeError):
            self.kazoo_client.delete(path, version=version, recursive=True)


class SchedulerEventQueue(ZooKeeperEventQueue):
    """Abstract API for tenant specific events via ZooKeeper

    The lifecycle of a global (not pipeline-specific) event is:

    * Serialized form of event added to ZK queue.

    * During queue processing, events are de-serialized and
      AbstractEvent subclasses are instantiated.  An EventAckRef is
      associated with the event instance in order to maintain the link
      to the serialized form.

    * When event processing is complete, the EventAckRef is used to
      delete the original event.  If the event requires a result
      (e.g., a management event that returns data) the result will be
      written to a pre-determined location.  A future can watch for
      the result to appear at that location.

    Pipeline specific events usually start out as global events, but
    upon processing, may be forwarded to pipeline-specific queues.  In
    these cases, the original event will be deleted as above, and a
    new, identical event will be created in the pipeline-specific
    queue.  If the event expects a result, no result will be written
    upon forwarding; the result will only be written when the
    forwarded event is processed.

    """

    log = logging.getLogger("zuul.zk.event_queues.SchedulerEventQueue")

    def __init__(self, client, event_root, event_prefix):
        super().__init__(client, event_root)
        self.event_prefix = event_prefix

    def _listEvents(self):
        return [
            e
            for e in self.kazoo_client.get_children(self.event_root)
            if e.startswith(self.event_prefix.value)
        ]

    @property
    def _event_create_path(self) -> str:
        return "{}/{}-".format(self.event_root, self.event_prefix.value)


class ManagementEventResultFuture(ZooKeeperSimpleBase):
    """Returned when a management event is put into a queue."""

    log = logging.getLogger("zuul.zk.event_queues.MangementEventResultFuture")

    def __init__(self, client, result_path):
        super().__init__(client)
        self._result_path = result_path
        self._wait_event = threading.Event()
        self.kazoo_client.DataWatch(self._result_path, self._resultCallback)

    def _resultCallback(self, data=None, stat=None):
        if data is None:
            # Igore events w/o any data
            return None
        self._wait_event.set()
        # Stop the watch if we got a result
        return False

    def wait(self, timeout=None):
        """Wait until the result for this event has been written."""

        # Note that due to event forwarding, the only way to confirm
        # that an event has been processed is to check for a result;
        # the original event may have been deleted when forwaded to a
        # different queue.
        if not self._wait_event.wait(timeout):
            return False
        try:
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


class ManagementEventQueue(SchedulerEventQueue):
    """Management events via ZooKeeper"""

    RESULTS_ROOT = "/zuul/results/management"

    log = logging.getLogger("zuul.zk.event_queues.ManagementEventQueue")

    def put(self, event, needs_result=True):
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
        if needs_result and not event.result_ref:
            # The event was not forwarded, create the result ref
            self.kazoo_client.create(result_path, None,
                                     makepath=True, ephemeral=True)
        self._put(data)
        if needs_result and result_path:
            return ManagementEventResultFuture(self.client, result_path)
        return None

    def __iter__(self):
        event_list = []
        for data, ack_ref, zstat in self._iterEvents():
            try:
                event_class = MANAGEMENT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
                result_path = data["result_path"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path, ack_ref.version)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            event.result_ref = result_path
            # Initialize the logical timestamp if not valid
            if event.zuul_event_ltime is None:
                event.zuul_event_ltime = zstat.creation_transaction_id

            with suppress(ValueError):
                other_event = event_list[event_list.index(event)]
                if isinstance(other_event, model.TenantReconfigureEvent):
                    other_event.merge(event)
                    continue
            event_list.append(event)
        yield from event_list

    def ack(self, event):
        """Acknowledge the event (by deleting it from the queue)"""
        # Note: the result is reported first to ensure that the
        # originator of the event which may be waiting on a future
        # receives a result, or otherwise this event is considered
        # unprocessed and remains on the queue.
        self._reportResult(event)
        super().ack(event)
        if isinstance(event, model.TenantReconfigureEvent):
            for merged_event in event.merged_events:
                merged_event.traceback = event.traceback
                self._reportResult(merged_event)
                super().ack(merged_event)

    def _reportResult(self, event):
        if not event.result_ref:
            return

        result_data = {"traceback": event.traceback,
                       "timestamp": time.monotonic()}
        try:
            self.kazoo_client.set(
                event.result_ref,
                json.dumps(result_data).encode("utf-8"),
            )
        except NoNodeError:
            self.log.warning(f"No result node found for {event}; "
                             "client may have disconnected")


class PipelineManagementEventQueue(ManagementEventQueue):
    log = logging.getLogger(
        "zuul.zk.event_queues.PipelineManagementEventQueue"
    )

    def __init__(self, client, tenant_name, pipeline_name):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, EventPrefix.MANAGEMENT)

    @classmethod
    def createRegistry(cls, client):
        """Create a tenant/pipeline queue registry

        Returns a nested dictionary of:
          tenant_name -> pipeline_name -> EventQueue

        Queues are dynamically created with the originally supplied ZK
        client as they are accessed via the registry (so new tenants
        or pipelines show up automatically).

        """
        return DefaultKeyDict(lambda t: cls._createRegistry(client, t))

    @classmethod
    def _createRegistry(cls, client, tenant_name):
        return DefaultKeyDict(lambda p: cls(client, tenant_name, p))


class GlobalManagementEventQueue(ManagementEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.GlobalManagementEventQueue")

    def __init__(self, client):
        super().__init__(client, SCHEDULER_GLOBAL_ROOT, EventPrefix.MANAGEMENT)

    def ackWithoutResult(self, event):
        """
        Used to ack a management event when forwarding to a pipeline queue
        """
        super(ManagementEventQueue, self).ack(event)
        if isinstance(event, model.TenantReconfigureEvent):
            for merged_event in event.merged_events:
                super(ManagementEventQueue, self).ack(merged_event)


class PipelineResultEventQueue(SchedulerEventQueue):
    """Result events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.PipelineResultEventQueue")

    def __init__(self, client, tenant_name, pipeline_name):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, EventPrefix.RESULT)

    @classmethod
    def createRegistry(cls, client):
        """Create a tenant/pipeline queue registry

        Returns a nested dictionary of:
          tenant_name -> pipeline_name -> EventQueue

        Queues are dynamically created with the originally supplied ZK
        client as they are accessed via the registry (so new tenants
        or pipelines show up automatically).

        """
        return DefaultKeyDict(lambda t: cls._createRegistry(client, t))

    @classmethod
    def _createRegistry(cls, client, tenant_name):
        return DefaultKeyDict(lambda p: cls(client, tenant_name, p))

    def put(self, event):
        data = {
            "event_type": type(event).__name__,
            "event_data": event.toDict(),
        }
        self._put(data)

    def __iter__(self):
        for data, ack_ref, _ in self._iterEvents():
            try:
                event_class = RESULT_EVENT_TYPE_MAP[data["event_type"]]
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path, ack_ref.version)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            yield event


class TriggerEventQueue(SchedulerEventQueue):
    """Trigger events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.TriggerEventQueue")

    def __init__(self, client, event_root, connections):
        self.connections = connections
        super().__init__(client, event_root, EventPrefix.TRIGGER)

    def put(self, driver_name, event):
        data = {
            "driver_name": driver_name,
            "event_data": event.toDict(),
        }
        self._put(data)

    def __iter__(self):
        for data, ack_ref, _ in self._iterEvents():
            try:
                event_class = self.connections.getTriggerEventClass(
                    data["driver_name"]
                )
                event_data = data["event_data"]
            except KeyError:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path, ack_ref.version)
                continue
            event = event_class.fromDict(event_data)
            event.ack_ref = ack_ref
            event.driver_name = data["driver_name"]
            yield event


class GlobalTriggerEventQueue(TriggerEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.GlobalTriggerEventQueue")

    def __init__(self, client, connections):
        super().__init__(client, SCHEDULER_GLOBAL_ROOT, connections)


class PipelineTriggerEventQueue(TriggerEventQueue):
    log = logging.getLogger("zuul.zk.event_queues.PipelineTriggerEventQueue")

    def __init__(self, client, tenant_name, pipeline_name, connections):
        event_root = "/".join((TENANT_ROOT, tenant_name, pipeline_name))
        super().__init__(client, event_root, connections)

    @classmethod
    def createRegistry(cls, client, connections):
        """Create a tenant/pipeline queue registry

        Returns a nested dictionary of:
          tenant_name -> pipeline_name -> EventQueue

        Queues are dynamically created with the originally supplied ZK
        client and connection registry as they are accessed via the
        queue registry (so new tenants or pipelines show up
        automatically).

        """
        return DefaultKeyDict(
            lambda t: cls._createRegistry(client, t, connections)
        )

    @classmethod
    def _createRegistry(cls, client, tenant_name, connections):
        return DefaultKeyDict(
            lambda p: cls(client, tenant_name, p, connections)
        )


class ConnectionEventQueue(ZooKeeperEventQueue):
    """Connection events via ZooKeeper"""

    log = logging.getLogger("zuul.zk.event_queues.ConnectionEventQueue")

    def __init__(self, client, connection_name):
        event_root = "/".join((CONNECTION_ROOT, connection_name, "events"))
        super().__init__(client, event_root)
        self.election_root = "/".join(
            (CONNECTION_ROOT, connection_name, "election")
        )
        self.kazoo_client.ensure_path(self.election_root)
        self.election = self.kazoo_client.Election(self.election_root)

    def _eventWatch(self, callback, event_list):
        if event_list:
            return callback()

    def registerEventWatch(self, callback):
        self.kazoo_client.ChildrenWatch(
            self.event_root, functools.partial(self._eventWatch, callback)
        )

    def put(self, data):
        self.log.debug("Submitting connection event to queue %s: %s",
                       self.event_root, data)
        self._put(data)

    def __iter__(self):
        for data, ack_ref, _ in self._iterEvents():
            if not data:
                self.log.warning("Malformed event found: %s", data)
                self._remove(ack_ref.path)
                continue
            event = model.ConnectionEvent.fromDict(data)
            event.ack_ref = ack_ref
            yield event


class EventReceiverElection(Election):
    """Election for a singleton event receiver."""

    def __init__(self, client, connection_name, receiver_name):
        self.election_root = "/".join(
            (CONNECTION_ROOT, connection_name, f"election-{receiver_name}")
        )
        super().__init__(client.client, self.election_root)
