# Copyright 2024 BMW Group
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
import random
import threading
import time
import uuid
from contextlib import suppress

from zuul import model
from zuul.zk import ZooKeeperClient
from zuul.zk.exceptions import LockException
from zuul.zk.launcher import LauncherClientApi, LauncherServerApi
from zuul.zk.locks import locked, SessionAwareLock
from zuul.zk.components import (
    ComponentRegistry,
    LauncherComponent,
    COMPONENT_REGISTRY
)

from tests.base import (
    BaseTestCase,
    iterate_timeout
)


class FakeLauncher:

    def __init__(
            self, launcher_name, zk_client, component_registry, providers):
        self.log = logging.getLogger(f"FakeLauncher.{launcher_name}")
        self.zk_client = zk_client
        self.launcher_name = launcher_name
        self.component_registry = component_registry
        self.wake_event = threading.Event()
        self.component_info = LauncherComponent(self.zk_client, launcher_name)
        self.component_info.register()
        self.api = LauncherServerApi(
            self.zk_client,
            self.component_registry,
            self.component_info,
            self.wake_event.set)
        self.worker = threading.Thread(target=self._run, name="fake-launcher")
        self._running = False
        self._interval = 1
        self.fail_labels = set()
        self.hold_nodes_in_build = False
        self.work_delay = 0.1
        self.providers = providers

    def start(self):
        self.log.debug("Starting launcher %s", self.launcher_name)
        self._running = True
        self.worker.start()

    def stop(self):
        self.log.debug("Stopping launcher %s", self.launcher_name)
        self._running = False
        self.wake_event.set()
        self.worker.join()
        self.api.stop()

    def _run(self):
        try:
            self.component_info.ready = True
            while self._running:
                self.wake_event.wait(self._interval)
                self.wake_event.clear()
                self.log.debug("Wake up")
                try:
                    self._process_nodes()
                    self._process_requests()
                except Exception:
                    self.log.exception("Error in launcher:")
                    self.wake_event.set()
        finally:
            self.component_info.ready = False

    def _process_nodes(self):
        for node in self.api.getMatchingProviderNodes():
            if not node.lock:
                if not self.api.lockNode(node, blocking=False):
                    self.log.debug("Failed to lock matching node %s", node)
                    continue
                # time.sleep(self.work_delay)
            if node.state == model.ProviderNode.STATE_REQUESTED:
                self._build_node(node)
            if node.state == model.ProviderNode.STATE_BUILDING:
                self._check_provider_node(node)

    def _build_node(self, node):
        self.log.debug("Building node %s", node)
        self.api.updateNode(
            node, state=model.ProviderNode.STATE_BUILDING)

    def _check_provider_node(self, node):
        self.log.debug("Checking node %s", node)
        if self.hold_nodes_in_build:
            return
        state = model.ProviderNode.STATE_READY
        if node.label in self.fail_labels:
            state = model.ProviderNode.STATE_FAILED
        self.log.debug("Marking node %s as %s", node, state)
        self.api.updateNode(node, state=state)
        self.api.unlockNode(node)

    def _process_requests(self):
        for request in self.api.getMatchingRequests():
            self.log.debug("Got request %s", request)
            if not request.lock:
                if not self.api.lockRequest(request, blocking=False):
                    self.log.debug(
                        "Failed to lock matching request %s", request)
                    continue
                time.sleep(self.work_delay)

            if request.state == model.NodesetRequest.STATE_REQUESTED:
                self._accept_request(request)
            elif request.state == model.NodesetRequest.STATE_ACCEPTED:
                self._check_request_nodes(request)

    def _accept_request(self, request):
        self.log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        provider = random.choice(self.providers)
        request_uuid = uuid.UUID(request.uuid)
        provider_nodes = []
        for i, label in enumerate(request.labels):
            # Create deterministic provider node UUID by using
            # the request UUID as namespace.
            node_uuid = uuid.uuid5(request_uuid,
                                   f"{provider}-{i}-{label}").hex
            node = model.ProviderNode(uuid=node_uuid, label=label)
            self.api.requestProviderNode(provider, node)
            self.log.debug("Requesting node %s", node)
            provider_nodes.append(node.path)

        # Accept and update the nodeset request
        self.api.updateNodesetRequest(
            request,
            state=model.NodesetRequest.STATE_ACCEPTED,
            provider_nodes=provider_nodes)

    def _check_request_nodes(self, request):
        self.log.debug("Checking request %s", request)
        requested_nodes = [self.api.getProviderNode(p)
                           for p in request.provider_nodes]
        if not all(n.state in model.ProviderNode.OK_STATES
                   for n in requested_nodes):
            self.log.debug("Request %s nodes not ready: %s",
                           request, requested_nodes)
            return
        failed = not all(n.state in model.ProviderNode.STATE_READY
                         for n in requested_nodes)
        state = (model.NodesetRequest.STATE_FAILED if failed
                 else model.NodesetRequest.STATE_FULFILLED)
        self.log.debug("Marking request %s as ", request)
        self.api.updateNodesetRequest(request, state=state)
        self.api.unlockRequest(request)


class FakeLauncherGlobalLocks:

    def __init__(
            self, launcher_name, zk_client, component_registry, providers):
        self.log = logging.getLogger(f"FakeLauncher2.{launcher_name}")
        self.zk_client = zk_client
        self.launcher_name = launcher_name
        self.component_registry = component_registry
        self.wake_event = threading.Event()
        self.component_info = LauncherComponent(self.zk_client, launcher_name)
        self.component_info.register()
        self.api = LauncherServerApi(
            self.zk_client,
            self.component_registry,
            self.component_info,
            self.wake_event.set)
        self.worker = threading.Thread(target=self._run, name="fake-launcher")
        self._running = False
        self._interval = 1
        self.fail_labels = set()
        self.hold_nodes_in_build = False
        self.work_delay = 0.1
        global_path = "/zuul/launcher-requests"
        self.global_lock = SessionAwareLock(self.zk_client.client, global_path)
        self.provider_locks = {
            p: SessionAwareLock(
                self.zk_client.client,
                f"/zuul/launcher-provider/{p}") for p in providers
        }
        self.providers = providers

    def start(self):
        self.log.debug("Starting launcher %s", self.launcher_name)
        self._running = True
        self.worker.start()

    def stop(self):
        self.log.debug("Stopping launcher %s", self.launcher_name)
        self._running = False
        self.wake_event.set()
        self.worker.join()
        self.api.stop()

    def _run(self):
        try:
            self.component_info.ready = True
            while self._running:
                self.wake_event.wait(self._interval)
                self.wake_event.clear()
                self.log.debug("Wake up")
                try:
                    with suppress(LockException):
                        for provider in self.providers:
                            with locked(self.provider_locks[provider],
                                        blocking=False):
                                self._process_nodes(provider)
                    with suppress(LockException):
                        with locked(self.global_lock, blocking=False):
                            self._process_requests()
                except Exception:
                    self.log.exception("Error in launcher:")
                    self.wake_event.set()
        finally:
            self.component_info.ready = False

    def _process_nodes(self, provider):
        for node in self.api.getProviderNodes():
            if node.provider != provider:
                continue
            if not node.lock:
                node.lock = True
                # time.sleep(self.work_delay)
            if node.state == model.ProviderNode.STATE_REQUESTED:
                self._build_node(node)
            if node.state == model.ProviderNode.STATE_BUILDING:
                self._check_provider_node(node)

    def _build_node(self, node):
        self.log.debug("Building node %s", node)
        self.api.updateNode(
            node, state=model.ProviderNode.STATE_BUILDING)

    def _check_provider_node(self, node):
        self.log.debug("Checking node %s", node)
        if self.hold_nodes_in_build:
            return
        state = model.ProviderNode.STATE_READY
        if node.label in self.fail_labels:
            state = model.ProviderNode.STATE_FAILED
        self.log.debug("Marking node %s as %s", node, state)
        self.api.updateNode(node, state=state)

    def _process_requests(self):
        for request in self.api.getNodesetRequests():
            if not request.lock:
                request.lock = True
                time.sleep(self.work_delay)
            self.log.debug("Got request %s", request)
            if request.state == model.NodesetRequest.STATE_REQUESTED:
                self._accept_request(request)
            elif request.state == model.NodesetRequest.STATE_ACCEPTED:
                self._check_request_nodes(request)

    def _accept_request(self, request):
        self.log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        provider = random.choice(self.providers)
        request_uuid = uuid.UUID(request.uuid)
        provider_nodes = []
        for i, label in enumerate(request.labels):
            # Create deterministic provider node UUID by using
            # the request UUID as namespace.
            node_uuid = uuid.uuid5(request_uuid,
                                   f"{provider}-{i}-{label}").hex
            node = model.ProviderNode(uuid=node_uuid, label=label)
            self.api.requestProviderNode(provider, node)
            self.log.debug("Requesting node %s", node)
            provider_nodes.append(node.path)

        # Accept and update the nodeset request
        self.api.updateNodesetRequest(
            request,
            state=model.NodesetRequest.STATE_ACCEPTED,
            provider_nodes=provider_nodes)

    def _check_request_nodes(self, request):
        self.log.debug("Checking request %s", request)
        requested_nodes = [self.api.getProviderNode(p)
                           for p in request.provider_nodes]
        if not all(n.state in model.ProviderNode.OK_STATES
                   for n in requested_nodes):
            self.log.debug("Request %s nodes not ready: %s",
                           request, requested_nodes)
            return
        failed = not all(n.state in model.ProviderNode.STATE_READY
                         for n in requested_nodes)
        state = (model.NodesetRequest.STATE_FAILED if failed
                 else model.NodesetRequest.STATE_FULFILLED)
        self.log.debug("Marking request %s as ", request)
        self.api.updateNodesetRequest(request, state=state)


class FakeLauncherNodepool:

    def __init__(
            self, launcher_name, zk_client, component_registry, providers):
        self.log = logging.getLogger(f"FakeLauncherNodepool.{launcher_name}")
        self.zk_client = zk_client
        self.launcher_name = launcher_name
        self.component_registry = component_registry
        self.wake_event = threading.Event()
        self.component_info = LauncherComponent(self.zk_client, launcher_name)
        self.component_info.register()
        self.api = LauncherServerApi(
            self.zk_client,
            self.component_registry,
            self.component_info,
            self.wake_event.set)
        self.worker = threading.Thread(target=self._run, name="fake-launcher")
        self._running = False
        self._interval = 1
        self.fail_labels = set()
        self.hold_nodes_in_build = False
        self.work_delay = 0.1
        self.providers = providers

    def start(self):
        self.log.debug("Starting launcher %s", self.launcher_name)
        self._running = True
        self.worker.start()

    def stop(self):
        self.log.debug("Stopping launcher %s", self.launcher_name)
        self._running = False
        self.wake_event.set()
        self.worker.join()
        self.api.stop()

    def _run(self):
        try:
            self.component_info.ready = True
            while self._running:
                self.wake_event.wait(self._interval)
                self.wake_event.clear()
                self.log.debug("Wake up")
                try:
                    self._process_nodes()
                    self._process_requests()
                except Exception:
                    self.log.exception("Error in launcher:")
                    self.wake_event.set()
        finally:
            self.component_info.ready = False

    def _process_nodes(self):
        for node in self.api.getProviderNodes():
            if not node.lock:
                if not self.api.lockNode(node, blocking=False):
                    self.log.debug("Failed to lock node %s", node)
                    continue
                # time.sleep(self.work_delay)
            if node.state == model.ProviderNode.STATE_REQUESTED:
                self._build_node(node)
            if node.state == model.ProviderNode.STATE_BUILDING:
                self._check_provider_node(node)

    def _build_node(self, node):
        self.log.debug("Building node %s", node)
        self.api.updateNode(
            node, state=model.ProviderNode.STATE_BUILDING)

    def _check_provider_node(self, node):
        self.log.debug("Checking node %s", node)
        if self.hold_nodes_in_build:
            return
        state = model.ProviderNode.STATE_READY
        if node.label in self.fail_labels:
            state = model.ProviderNode.STATE_FAILED
        self.log.debug("Marking node %s as %s", node, state)
        self.api.updateNode(node, state=state)
        self.api.unlockNode(node)

    def _process_requests(self):
        for request in self.api.getNodesetRequests():
            self.log.debug("Got request %s", request)
            if not request.lock:
                if not self.api.lockRequest(request, blocking=False):
                    self.log.debug(
                        "Failed to lock request %s", request)
                    continue
                time.sleep(self.work_delay)

            if request.state == model.NodesetRequest.STATE_REQUESTED:
                self._accept_request(request)
            elif request.state == model.NodesetRequest.STATE_ACCEPTED:
                self._check_request_nodes(request)

    def _accept_request(self, request):
        self.log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        provider = random.choice(self.providers)
        request_uuid = uuid.UUID(request.uuid)
        provider_nodes = []
        for i, label in enumerate(request.labels):
            # Create deterministic provider node UUID by using
            # the request UUID as namespace.
            node_uuid = uuid.uuid5(request_uuid,
                                   f"{provider}-{i}-{label}").hex
            node = model.ProviderNode(uuid=node_uuid, label=label)
            self.api.requestProviderNode(provider, node)
            self.log.debug("Requesting node %s", node)
            provider_nodes.append(node.path)

        # Accept and update the nodeset request
        self.api.updateNodesetRequest(
            request,
            state=model.NodesetRequest.STATE_ACCEPTED,
            provider_nodes=provider_nodes)

    def _check_request_nodes(self, request):
        self.log.debug("Checking request %s", request)
        requested_nodes = [self.api.getProviderNode(p)
                           for p in request.provider_nodes]
        if not all(n.state in model.ProviderNode.OK_STATES
                   for n in requested_nodes):
            self.log.debug("Request %s nodes not ready: %s",
                           request, requested_nodes)
            return
        failed = not all(n.state in model.ProviderNode.STATE_READY
                         for n in requested_nodes)
        state = (model.NodesetRequest.STATE_FAILED if failed
                 else model.NodesetRequest.STATE_FULFILLED)
        self.log.debug("Marking request %s as ", request)
        self.api.updateNodesetRequest(request, state=state)
        self.api.unlockRequest(request)


class TestLauncher(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.setupZK()
        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()
        self.component_registry = ComponentRegistry(self.zk_client)
        # We don't have any other component to initialize the global
        # registry in these tests, so we do it ourselves.
        COMPONENT_REGISTRY.create(self.zk_client)
        self.client = LauncherClientApi(self.zk_client)

    def create_launchers(self, count=1, start_index=0, klass=FakeLauncher,
                         providers=None):
        launchers = []
        providers = providers or ["dummy-provider"]
        for i in range(start_index, start_index + count):
            launcher = klass(
                f"launcher-{i}", self.zk_client, self.component_registry,
                providers)
            launcher.start()
            self.addCleanup(launcher.stop)
            launchers.append(launcher)
        return launchers

    def test_launcher(self):
        launcher = FakeLauncher(
            "fake-launcher", self.zk_client, self.component_registry,
            ["dummy-provider"])
        launcher.start()
        self.addCleanup(launcher.stop)

        labels = ["foo", "bar"]
        request = model.NodesetRequest(labels)
        self.client.submit(request)

        for _ in iterate_timeout(10, "request to be fulfilled"):
            self.client.refresh(request)
            if request.state == model.NodesetRequest.STATE_FULFILLED:
                break

    def test_multi_launcher(self):
        self.create_launchers(
            count=5, providers=["region-1", "region-2", "region-3"])

        requests = []
        for i in range(50):
            labels = ["foo", "bar"]
            request = model.NodesetRequest(labels)
            self.client.submit(request)
            requests.append(request)

        for _ in iterate_timeout(30, "request to be fulfilled"):
            for r in requests:
                self.client.refresh(r)
            if all(r.state == model.NodesetRequest.STATE_FULFILLED
                   for r in requests):
                break
            time.sleep(1)

    def test_multi_launcher_global_locks(self):
        self.create_launchers(
            count=5, klass=FakeLauncherGlobalLocks,
            providers=["region-1", "region-2", "region-3"])

        requests = []
        for i in range(50):
            labels = ["foo", "bar"]
            request = model.NodesetRequest(labels)
            self.client.submit(request)
            requests.append(request)

        for _ in iterate_timeout(30, "request to be fulfilled"):
            for r in requests:
                self.client.refresh(r)
            if all(r.state == model.NodesetRequest.STATE_FULFILLED
                   for r in requests):
                break
            time.sleep(1)

    def test_multi_launcher_nodepool(self):
        self.create_launchers(
            count=5, klass=FakeLauncherNodepool,
            providers=["region-1", "region-2", "region-3"])

        requests = []
        for i in range(50):
            labels = ["foo", "bar"]
            request = model.NodesetRequest(labels)
            self.client.submit(request)
            requests.append(request)

        for _ in iterate_timeout(30, "request to be fulfilled"):
            for r in requests:
                self.client.refresh(r)
            if all(r.state == model.NodesetRequest.STATE_FULFILLED
                   for r in requests):
                break
            time.sleep(1)

    def test_launcher_failover(self):
        launcher = FakeLauncher(
            "fake-launcher", self.zk_client, self.component_registry)
        launcher.hold_nodes_in_build = True
        try:
            launcher.start()

            labels = ["foo", "bar"]
            nodeset_request = model.NodesetRequest(labels)
            self.client.submit(nodeset_request)

            for _ in iterate_timeout(10, "request to be accepted"):
                self.client.refresh(nodeset_request)
                if (nodeset_request.state
                        == model.NodesetRequest.STATE_ACCEPTED):
                    break
                time.sleep(0.1)

            requests = launcher.api.getNodesetRequests()
            nodes = launcher.api.getProviderNodes()
        finally:
            launcher.stop()

        # We need to unlock all nodes and requests as we are using the
        # same ZK client, so the locks are still valid.
        for node in nodes:
            if node.lock:
                launcher.api.unlockNode(node)
        for request in requests:
            if request.lock:
                launcher.api.unlockRequest(request)

        self.create_launchers(count=1, start_index=1)
        for _ in iterate_timeout(30, "request to be fulfilled"):
            self.client.refresh(nodeset_request)
            if nodeset_request.state == model.NodesetRequest.STATE_FULFILLED:
                break
            time.sleep(0.1)
