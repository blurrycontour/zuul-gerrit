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

from zuul.lib import commandsocket, tracing
from zuul.lib.config import get_default
from zuul.version import get_version_string
from zuul.zk import ZooKeeperClient
from zuul.zk.components import LauncherComponent
from zuul.zk.event_queues import PipelineResultEventQueue

COMMANDS = (
    commandsocket.StopCommand,
)


class Launcher:
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, config, connections):
        self._running = False
        self.config = config
        self.connections = connections

        self.tracing = tracing.Tracing(self.config)
        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        self.hostname = socket.getfqdn()
        self.component_info = LauncherComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()

        self.command_map = {
            commandsocket.StopCommand.name: self.stop,
        }
        command_socket = get_default(
            self.config, "launcher", "command_socket",
            "/var/lib/zuul/launcher.socket")
        self.command_socket = commandsocket.CommandSocket(command_socket)
        self._command_running = False

        self.launcher_thread = threading.Thread(
            target=self.run,
            name="Launcher",
        )
        self.wake_event = threading.Event()

    def run(self):
        while self._running:
            self.wake_event.wait()
            self.wake_event.clear()

    def start(self):
        self.log.debug("Starting launcher thread")
        self._running = True
        self.launcher_thread.start()

        self.log.debug("Starting command processor")
        self._command_running = True
        self.command_socket.start()
        self.command_thread = threading.Thread(
            target=self.runCommand, name="command")
        self.command_thread.daemon = True
        self.command_thread.start()
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
