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
import socket
import threading
import uuid

from zuul import model
from zuul.lib import commandsocket, tracing
from zuul.lib.config import get_default
from zuul.version import get_version_string
from zuul.zk import ZooKeeperClient
from zuul.zk.components import COMPONENT_REGISTRY, LauncherComponent
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.launcher import LauncherApi
from zuul.zk.zkobject import ZKContext

COMMANDS = (
    commandsocket.StopCommand,
)

# TODO:
# - get a request specific logger


class FakeProviderNode(model.ProviderNode, subclass_id="fake"):
    pass


class Launcher:
    WATERMARK_SLEEP = 1
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, config):
        self.config = config
        self.wake_event = threading.Event()
        self.stop_event = threading.Event()

        self.tracing = tracing.Tracing(self.config)
        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        COMPONENT_REGISTRY.create(self.zk_client)
        self.hostname = socket.getfqdn()
        self.component_info = LauncherComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()

        self.connection_filter = get_default(
            self.config, "launcher", "connection_filter")
        self.api = LauncherApi(
            self.zk_client, COMPONENT_REGISTRY.registry, self.component_info,
            self.wake_event.set, self.connection_filter)

        self.command_map = {
            commandsocket.StopCommand.name: self.stop,
        }
        command_socket = get_default(
            self.config, "launcher", "command_socket",
            "/var/lib/zuul/launcher.socket")
        self.command_socket = commandsocket.CommandSocket(command_socket)
        self._command_running = False

        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        self.launcher_thread = threading.Thread(
            target=self.run,
            name="Launcher",
        )

    def run(self):
        self.component_info.state = self.component_info.RUNNING
        self.log.debug("Launcher running")
        while not self.stop_event.is_set():
            self.log.debug("Launcher awake")
            try:
                self._processRequests()
                self._processNodes()
            except Exception:
                self.log.exception("Error in launcher:")

            self.wake_event.wait(self.WATERMARK_SLEEP)
            self.wake_event.clear()

    def _processRequests(self):
        for request in self.api.getMatchingRequests():
            if not request.hasLock():
                if request.state in request.FINAL_STATES:
                    # Nothing to do here
                    continue
                self.log.debug("Got request %s", request)
                if not request.acquireLock(self.zk_client, blocking=False):
                    self.log.debug(
                        "Failed to lock matching request %s", request)
                    continue

            if request.state == model.NodesetRequest.State.REQUESTED:
                self._acceptRequest(request)
            elif request.state == model.NodesetRequest.State.ACCEPTED:
                self._checkRequest(request)
            elif request.state in request.FINAL_STATES:
                request.releaseLock()

    def _acceptRequest(self, request):
        self.log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        request_uuid = uuid.UUID(request.uuid)
        provider_nodes = []
        with self.createZKContext(request._lock, self.log) as ctx:
            for i, (connection_name, label) in enumerate(
                    self._selectConnection(request)):
                # Create a deterministic node UUID by using
                # the request UUID as namespace.
                node_uuid = uuid.uuid5(request_uuid,
                                       f"{connection_name}-{i}-{label}").hex
                # FIXME:
                # - Remove fake provider node
                # - Handle NodeExists errors
                node = FakeProviderNode.new(
                    ctx, uuid=node_uuid, label=label, request_id=request.uuid,
                    connection_name=connection_name)
                self.log.debug("Requested node %s", node)
                provider_nodes.append(node.uuid)

            request.updateAttributes(
                ctx,
                state=model.NodesetRequest.State.ACCEPTED,
                provider_nodes=provider_nodes)

    def _selectConnection(self, request):
        # FIXME: make connection selection more "sophisticated" :D
        return [("fake", label) for label in request.labels]

    def _checkRequest(self, request):
        self.log.debug("Checking request %s", request)
        requested_nodes = [self.api.getProviderNode(p)
                           for p in request.provider_nodes]
        if not all(n.state in n.FINAL_STATES for n in requested_nodes):
            return
        self.log.debug("Request %s nodes ready: %s", request, requested_nodes)
        failed = not all(n.state in model.ProviderNode.State.READY
                         for n in requested_nodes)
        # TODO:
        # * gracefully handle node failures (retry with another connection)
        # * deallocate ready nodes from the request if finally failed

        state = (model.NodesetRequest.State.FAILED if failed
                 else model.NodesetRequest.State.FULFILLED)
        self.log.debug("Marking request %s as %s", request, state)

        event = model.NodesProvisionedEvent(
            request.uuid, request.buildset_uuid)
        self.result_events[request.tenant_name][request.pipeline_name].put(
            event)

        with self.createZKContext(request._lock, self.log) as ctx:
            request.updateAttributes(ctx, state=state)

    def _processNodes(self):
        for node in self.api.getMatchingProviderNodes():
            if not node.hasLock():
                if node.state in node.FINAL_STATES:
                    continue
                if not node.acquireLock(self.zk_client, blocking=False):
                    self.log.debug("Failed to lock matching node %s", node)
                    continue
            if node.state == model.ProviderNode.State.REQUESTED:
                self._buildNode(node)
            if node.state == model.ProviderNode.State.BUILDING:
                self._checkNode(node)
            if node.state in node.FINAL_STATES:
                node.releaseLock()

    def _buildNode(self, node):
        self.log.debug("Building node %s", node)
        with self.createZKContext(node._lock, self.log) as ctx:
            node.updateAttributes(ctx, state=model.ProviderNode.State.BUILDING)

    def _checkNode(self, node):
        self.log.debug("Checking node %s", node)
        # FIXME: Handle failing node
        if True:
            state = model.ProviderNode.State.READY
        else:
            state = model.ProviderNode.State.FAILED
        self.log.debug("Marking node %s as %s", node, state)
        with self.createZKContext(node._lock, self.log) as ctx:
            node.updateAttributes(ctx, state=state)
        node.releaseLock()

    def start(self):
        self.log.debug("Starting launcher thread")
        self.launcher_thread.start()

        self.log.debug("Starting command processor")
        self._command_running = True
        self.command_socket.start()
        self.command_thread = threading.Thread(
            target=self.runCommand, name="command")
        self.command_thread.daemon = True
        self.command_thread.start()

    def stop(self):
        self.log.debug("Stopping launcher")
        self.stop_event.set()
        self.wake_event.set()
        self.component_info.state = self.component_info.STOPPED
        self._command_running = False
        self.command_socket.stop()
        self.log.debug("Stopped launcher")

    def join(self):
        self.log.debug("Joining launcher")
        self.launcher_thread.join()
        self.api.stop()
        self.zk_client.disconnect()
        self.tracing.stop()
        self.log.debug("Joined launcher")

    def runCommand(self):
        while self._command_running:
            try:
                command, args = self.command_socket.get()
                if command != '_stop':
                    self.command_map[command](*args)
            except Exception:
                self.log.exception("Exception while processing command")

    def createZKContext(self, lock, log):
        return ZKContext(self.zk_client, lock, self.stop_event, log)
