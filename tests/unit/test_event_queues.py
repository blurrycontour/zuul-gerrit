# Copyright 2021 BMW Group
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

from unittest.mock import patch

import testtools

from zuul import model
from zuul.driver import Driver, TriggerInterface
from zuul.lib.connections import ConnectionRegistry
from zuul.zk import ZooKeeperClient, event_queues

from tests.base import BaseTestCase


class EventQueueBaseTestCase(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca
        )
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()

        self.connections = ConnectionRegistry()
        self.addCleanup(self.connections.stop)


class DummyEvent(model.AbstractEvent):

    def toDict(self):
        return {}

    def updateFromDict(self):
        pass

    @classmethod
    def fromDict(cls, d):
        return cls()


class DummyPrefix:
    value = "dummy"


class DummyEventQueue(event_queues.ZooKeeperEventQueue):

    def put(self, event):
        self._put(event.toDict())

    def __iter__(self):
        for data, ack_ref in self._iterEvents():
            event = DummyEvent.fromDict(data)
            event.ack_ref = ack_ref
            yield event


class TestEventQueue(EventQueueBaseTestCase):

    def setUp(self):
        super().setUp()
        self.queue = DummyEventQueue(self.zk_client, "root", DummyPrefix())

    def test_missing_ack_ref(self):
        # Every event from a ZK event queue should have an ack_ref
        # attached to it when it is deserialized; ensure that an error
        # is raised if we try to ack an event without one.
        with testtools.ExpectedException(RuntimeError):
            self.queue.ack(DummyEvent())

    def test_double_ack(self):
        # Test that if we ack an event twice, an exception isn't
        # raised.
        self.queue.put(DummyEvent())
        self.assertEqual(len(self.queue), 1)

        event = next(iter(self.queue))
        self.queue.ack(event)
        self.assertEqual(len(self.queue), 0)

        # Should not raise an exception
        self.queue.ack(event)

    def test_invalid_json_ignored(self):
        # Test that invalid json is automatically removed.
        event_path = self.queue._put({})
        self.zk_client.client.set(event_path, b"{ invalid")

        self.assertEqual(len(self.queue), 1)
        self.assertEqual(list(self.queue._iterEvents()), [])
        self.assertEqual(len(self.queue), 0)


class DummyTriggerEvent(model.TriggerEvent):
    pass


class DummyDriver(Driver, TriggerInterface):
    name = driver_name = "dummy"

    def getTrigger(self, connection, config=None):
        pass

    def getTriggerSchema(self):
        pass

    def getTriggerEventClass(self):
        return DummyTriggerEvent


class TestTriggerEventQueue(EventQueueBaseTestCase):

    def setUp(self):
        super().setUp()
        self.driver = DummyDriver()
        self.connections.registerDriver(self.driver)

    def test_global_trigger_events(self):
        # Test enqueue/dequeue of the global trigger event queue.
        queue = event_queues.GlobalTriggerEventQueue(
            self.zk_client, self.connections
        )

        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

        event = DummyTriggerEvent()
        queue.put(self.driver.driver_name, event)
        queue.put(self.driver.driver_name, event)

        self.assertEqual(len(queue), 2)
        self.assertTrue(queue.hasEvents())

        processed = 0
        for event in queue:
            self.assertIsInstance(event, DummyTriggerEvent)
            processed += 1

        self.assertEqual(processed, 2)
        self.assertEqual(len(queue), 2)
        self.assertTrue(queue.hasEvents())

        acked = 0
        for event in queue:
            queue.ack(event)
            acked += 1

        self.assertEqual(acked, 2)
        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

    def test_pipeline_trigger_events(self):
        # Test enqueue/dequeue of pipeline-specific trigger event
        # queues.
        registry = event_queues.PipelineTriggerEventQueue.createRegistry(
            self.zk_client, self.connections
        )

        queue = registry["tenant"]["pipeline"]
        self.assertIsInstance(queue, event_queues.TriggerEventQueue)

        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

        event = DummyTriggerEvent()
        queue.put(self.driver.driver_name, event)

        self.assertEqual(len(queue), 1)
        self.assertTrue(queue.hasEvents())

        other_queue = registry["other_tenant"]["pipeline"]
        self.assertEqual(len(other_queue), 0)
        self.assertFalse(other_queue.hasEvents())

        acked = 0
        for event in queue:
            self.assertIsInstance(event, DummyTriggerEvent)
            queue.ack(event)
            acked += 1

        self.assertEqual(acked, 1)
        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())


class TestManagementEventQueue(EventQueueBaseTestCase):

    def test_management_events(self):
        # Test enqueue/dequeue of the global management event queue.
        queue = event_queues.GlobalManagementEventQueue(self.zk_client)

        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

        event = model.ReconfigureEvent(None)
        result_future = queue.put(event, needs_result=False)
        self.assertIsNone(result_future)

        result_future = queue.put(event)
        self.assertIsNotNone(result_future)

        self.assertEqual(len(queue), 2)
        self.assertTrue(queue.hasEvents())
        self.assertFalse(result_future.wait(0.1))

        acked = 0
        for event in queue:
            self.assertIsInstance(event, model.ReconfigureEvent)
            queue.ack(event)
            acked += 1

        self.assertEqual(acked, 2)
        self.assertTrue(result_future.wait(5))
        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

    def test_management_event_error(self):
        # Test that management event errors are reported.
        queue = event_queues.GlobalManagementEventQueue(self.zk_client)
        event = model.ReconfigureEvent(None)
        result_future = queue.put(event)

        acked = 0
        for event in queue:
            event.traceback = "hello traceback"
            queue.ack(event)
            acked += 1

        self.assertEqual(acked, 1)
        with testtools.ExpectedException(RuntimeError, msg="hello traceback"):
            self.assertFalse(result_future.wait(5))

    def test_event_merge(self):
        # Test that similar management events (eg, reconfiguration of
        # two projects) can be merged.
        queue = event_queues.GlobalManagementEventQueue(self.zk_client)
        event = model.TenantReconfigureEvent("tenant", "project", "master")
        queue.put(event, needs_result=False)
        event = model.TenantReconfigureEvent("tenant", "other", "branch")
        queue.put(event, needs_result=False)

        self.assertEqual(len(queue), 2)
        events = list(queue)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(len(event.merged_events), 1)
        self.assertEqual(
            event.project_branches,
            set([("project", "master"), ("other", "branch")])
        )

        queue.ack(event)
        self.assertFalse(queue.hasEvents())

    def test_pipeline_management_events(self):
        # Test that when a management event is forwarded from the
        # global to the a pipeline-specific queue, it is not
        # prematurely acked and the future returns correctly.
        global_queue = event_queues.GlobalManagementEventQueue(self.zk_client)
        registry = event_queues.PipelineManagementEventQueue.createRegistry(
            self.zk_client
        )

        event = model.PromoteEvent('tenant', 'check', ['1234,1'])
        result_future = global_queue.put(event, needs_result=False)
        self.assertIsNone(result_future)

        result_future = global_queue.put(event)
        self.assertIsNotNone(result_future)

        self.assertEqual(len(global_queue), 2)
        self.assertTrue(global_queue.hasEvents())

        pipeline_queue = registry["tenant"]["pipeline"]
        self.assertIsInstance(
            pipeline_queue, event_queues.ManagementEventQueue
        )
        acked = 0
        for event in global_queue:
            self.assertIsInstance(event, model.PromoteEvent)
            # Forward event to pipeline management event queue
            pipeline_queue.put(event)
            global_queue.ackWithoutResult(event)
            acked += 1

        self.assertEqual(acked, 2)
        # Event was just forwarded and since we expect a result, the
        # future should not be completed yet.
        self.assertFalse(result_future.wait(0.1))

        self.assertEqual(len(global_queue), 0)
        self.assertFalse(global_queue.hasEvents())

        self.assertEqual(len(pipeline_queue), 2)
        self.assertTrue(pipeline_queue.hasEvents())

        acked = 0
        for event in pipeline_queue:
            self.assertIsInstance(event, model.PromoteEvent)
            pipeline_queue.ack(event)
            acked += 1

        self.assertEqual(acked, 2)
        self.assertTrue(result_future.wait(5))
        self.assertEqual(len(pipeline_queue), 0)
        self.assertFalse(pipeline_queue.hasEvents())


# TODO: use actual model.ResultEvent once it inherits from
# AbstractEvent and implements serialization.
class DummyResultEvent(model.ResultEvent, DummyEvent):
    pass


@patch.dict(event_queues.RESULT_EVENT_TYPE_MAP,
            {"DummyResultEvent": DummyResultEvent})
class TestResultEventQueue(EventQueueBaseTestCase):

    def test_pipeline_result_events(self):
        # Test enqueue/dequeue of result events.
        registry = event_queues.PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        queue = registry["tenant"]["pipeline"]
        self.assertIsInstance(queue, event_queues.PipelineResultEventQueue)

        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())

        event = DummyResultEvent()
        queue.put(event)

        self.assertEqual(len(queue), 1)
        self.assertTrue(queue.hasEvents())

        other_queue = registry["other_tenant"]["pipeline"]
        self.assertEqual(len(other_queue), 0)
        self.assertFalse(other_queue.hasEvents())

        acked = 0
        for event in queue:
            self.assertIsInstance(event, DummyResultEvent)
            queue.ack(event)
            acked += 1

        self.assertEqual(acked, 1)
        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.hasEvents())
