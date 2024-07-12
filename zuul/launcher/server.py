# Copyright 2024 BMW Group
# Copyright 2024 Acme Gating, LLC
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

from zuul.lib import commandsocket, tracing
from zuul.lib.config import get_default
from zuul.zk.image_registry import ImageBuildRegistry
from zuul.version import get_version_string
from zuul.zk import ZooKeeperClient
from zuul.zk.components import LauncherComponent
from zuul.zk.event_queues import (
    PipelineResultEventQueue,
    TenantTriggerEventQueue,
)
from zuul.zk.layout import (
    LayoutProvidersStore,
    LayoutStateStore,
)
from zuul.zk.locks import tenant_read_lock
from zuul.zk.zkobject import ZKContext

COMMANDS = (
    commandsocket.StopCommand,
)


class Launcher:
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, config, connections):
        self._running = False
        self.config = config
        self.connections = connections
        self.tenant_providers = {}

        self.tracing = tracing.Tracing(self.config)
        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        self.trigger_events = TenantTriggerEventQueue.createRegistry(
            self.zk_client, self.connections
        )
        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        self.hostname = socket.getfqdn()
        self.component_info = LauncherComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()
        self.wake_event = threading.Event()

        self.command_map = {
            commandsocket.StopCommand.name: self.stop,
        }
        command_socket = get_default(
            self.config, "launcher", "command_socket",
            "/var/lib/zuul/launcher.socket")
        self.command_socket = commandsocket.CommandSocket(command_socket)
        self._command_running = False

        self.tenant_layout_state = LayoutStateStore(
            self.zk_client, self.wake_event.set)
        self.layout_providers_store = LayoutProvidersStore(
            self.zk_client, self.connections)
        self.local_layout_state = {}

        self.image_build_registry = ImageBuildRegistry(self.zk_client)

        self.launcher_thread = threading.Thread(
            target=self.run,
            name="Launcher",
        )

    def run(self):
        while self._running:
            self.wake_event.wait()
            self.wake_event.clear()
            try:
                self._run()
            except Exception:
                self.log.exception("Error in main thread:")

    def _run(self):
        if self.updateTenantProviders():
            self.checkMissingImages()

    def start(self):
        self.log.debug("Starting command processor")
        self._command_running = True
        self.command_socket.start()
        self.command_thread = threading.Thread(
            target=self.runCommand, name="command")
        self.command_thread.daemon = True
        self.command_thread.start()

        self.log.debug("Starting launcher thread")
        self._running = True
        self.launcher_thread.start()

        self.component_info.state = self.component_info.RUNNING

    def stop(self):
        self.log.debug("Stopping launcher")
        self._running = False
        self.wake_event.set()
        self.component_info.state = self.component_info.STOPPED
        self._command_running = False
        self.command_socket.stop()
        self.connections.stop()
        self.log.debug("Stopped launcher")

    def join(self):
        self.log.debug("Joining launcher")
        self.launcher_thread.join()
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
        return ZKContext(self.zk_client, lock, None, log)

    def updateTenantProviders(self):
        # We need to handle new and deleted tenants, so we need to
        # process all tenants currently known and the new ones.
        tenant_names = set(self.tenant_providers.keys())
        tenant_names.update(self.tenant_layout_state)

        updated = False
        for tenant_name in tenant_names:
            # Reload the tenant if the layout changed.
            if self._updateTenantProviders(tenant_name):
                updated = True
        return updated

    def _updateTenantProviders(self, tenant_name):
        # Reload the tenant if the layout changed.
        updated = False
        if (self.local_layout_state.get(tenant_name)
                == self.tenant_layout_state.get(tenant_name)):
            return updated
        self.log.debug("Updating tenant %s", tenant_name)
        with tenant_read_lock(self.zk_client, tenant_name, self.log) as tlock:
            layout_state = self.tenant_layout_state.get(tenant_name)

            if layout_state:
                with self.createZKContext(tlock, self.log) as context:
                    providers = list(self.layout_providers_store.get(
                        context, tenant_name))
                    self.tenant_providers[tenant_name] = providers
                    for provider in providers:
                        self.log.debug("Loaded provider %s", provider.name)
                self.local_layout_state[tenant_name] = layout_state
                updated = True
            else:
                self.tenant_providers.pop(tenant_name, None)
                self.local_layout_state.pop(tenant_name, None)
        return updated

    def addImageBuildEvent(self, tenant_name, image):
        project_hostname, project_name = \
            image.project_canonical_name.split('/', 1)
        driver = self.connections.drivers['zuul']
        event = driver.getImageBuildEvent(
            image.name, project_hostname, project_name, image.branch)
        self.log.info("Submitting image build event for %s %s",
                      tenant_name, image.name)
        self.trigger_events[tenant_name].put(event.trigger_name, event)

    def checkMissingImages(self):
        for tenant_name, providers in self.tenant_providers.items():
            for provider in providers:
                for image in provider.images:
                    if image.type == 'zuul':
                        self.checkMissingImage(tenant_name, image)

    def checkMissingImage(self, tenant_name, image):
        # If there is already a successful build for
        # this image, skip.
        # get the registry for the image name

        seen_formats = set()
        for build in self.image_build_registry.getArtifactsForImage(
                image.canonical_name):
            seen_formats.add(build.format)

        if seen_formats >= image.formats:
            # We have at least one build with the required
            # formats
            return
        self.addImageBuildEvent(tenant_name, image)
