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

from zuul.lib.fingergw import FingerGateway
from zuul.zk import ZooKeeperClient
from zuul.zk.components import ZooKeeperComponentRegistry

from tests.base import ZuulTestCase, ZuulWebFixture


class TestComponentRegistry(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'

    def setUp(self):
        super().setUp()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca,
        )
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()
        self.component_registry = ZooKeeperComponentRegistry(self.zk_client)

    def test_scheduler_component(self):
        component_states = self.component_registry.all("schedulers")
        self.assertEqual(len(component_states), 1)

        component = component_states[0]
        self.assertEqual(component.get("state"), component.RUNNING)

    def test_executor_component(self):
        component_states = self.component_registry.all("executors")
        self.assertEqual(len(component_states), 1)

        component = component_states[0]
        self.assertEqual(component.get("state"), component.RUNNING)

        self.executor_server.pause()
        component = self.component_registry.all("executors")[0]
        self.assertEqual(component.get("state"), component.PAUSED)

        self.executor_server.unpause()
        component = self.component_registry.all("executors")[0]
        self.assertEqual(component.get("state"), component.RUNNING)

    def test_merger_component(self):
        component_states = self.component_registry.all("mergers")
        self.assertEqual(len(component_states), 0)

        self._startMerger()

        component_states = self.component_registry.all("mergers")
        self.assertEqual(len(component_states), 1)

        component = component_states[0]
        self.assertEqual(component.get("state"), component.RUNNING)

        self.merge_server.pause()
        component = self.component_registry.all("mergers")[0]
        self.assertEqual(component.get("state"), component.PAUSED)

        self.merge_server.unpause()
        component = self.component_registry.all("mergers")[0]
        self.assertEqual(component.get("state"), component.RUNNING)

        self.merge_server.stop()
        self.merge_server.join()
        # Set the merger to None so the test doesn't try to stop it again
        self.merge_server = None

        component_states = self.component_registry.all("mergers")
        self.assertEqual(len(component_states), 0)

    def test_fingergw_component(self):
        component_states = self.component_registry.all("finger-gateways")
        self.assertEqual(len(component_states), 0)

        gateway = FingerGateway(
            self.config,
            ("127.0.0.1", self.gearman_server.port, None, None, None),
            ("127.0.0.1", 0),
            user=None,
            command_socket=None,
            pid_file=None
        )
        gateway.start()

        try:
            component_states = self.component_registry.all("finger-gateways")
            self.assertEqual(len(component_states), 1)

            component = component_states[0]
            self.assertEqual(component.get("state"), component.RUNNING)
        finally:
            gateway.stop()
            gateway.wait()

        component_states = self.component_registry.all("finger-gateways")
        self.assertEqual(len(component_states), 0)

    def test_web_component(self):
        component_states = self.component_registry.all("finger-gateways")
        self.assertEqual(len(component_states), 0)

        self.useFixture(
            ZuulWebFixture(
                self.changes, self.config, self.additional_event_queues,
                self.upstream_root, self.rpcclient, self.poller_events,
                self.git_url_with_auth, self.addCleanup, self.test_root
            )
        )

        component_states = self.component_registry.all("webs")
        self.assertEqual(len(component_states), 1)

        component = component_states[0]
        self.assertEqual(component.get("state"), component.RUNNING)
