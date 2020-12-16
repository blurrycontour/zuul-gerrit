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

from tests.base import (
    iterate_timeout,
    ZuulTestCase,
)


class TestScaleOutScheduler(ZuulTestCase):
    tenant_config_file = "config/single-tenant/main.yaml"

    def create_scheduler(self):
        self.scheds.create(
            self.log,
            self.config,
            self.zk_config,
            self.changes,
            self.additional_event_queues,
            self.upstream_root,
            self.rpcclient,
            self.poller_events,
            self.git_url_with_auth,
            self.source_only,
            self.fake_sql,
            self.addCleanup,
        )

    def test_config_priming(self):
        for _ in iterate_timeout(10, "Wait until priming is complete"):
            layout_state = self.scheds.first.sched.tenant_layout_state.get(
                "tenant-one"
            )
            if layout_state is not None:
                break

        # Second scheduler instance
        self.create_scheduler()
        self.assertEqual(len(self.scheds), 2)

        for _ in iterate_timeout(
            10, "Wait for all schedulers to have the same layout state"
        ):
            layout_states = [
                a.sched.local_layout_state["tenant-one"]
                for a in self.scheds.instances
            ]
            if all(l == layout_state for l in layout_states):
                break

        for app in self.scheds.instances:
            if app is self.scheds.first:
                self.assertIsNotNone(
                    app.sched.merger.history.get("merger:cat")
                )
            else:
                # Make sure the other schedulers did not issue any cat jobs
                self.assertIsNone(app.sched.merger.history.get("merger:cat"))

    def test_reconfigure(self):
        # Create a second scheduler instance
        self.create_scheduler()
        self.assertEqual(len(self.scheds), 2)

        for _ in iterate_timeout(10, "Wait until priming is complete"):
            old = self.scheds.first.sched.tenant_layout_state.get("tenant-one")
            if old is not None:
                break

        for _ in iterate_timeout(
            10, "Wait for all schedulers to have the same layout state"
        ):
            layout_states = [
                a.sched.local_layout_state["tenant-one"]
                for a in self.scheds.instances
            ]
            if all(l == old for l in layout_states):
                break

        self.scheds.first.sched.reconfigure(self.scheds.first.config)
        self.waitUntilSettled()

        new = self.scheds.first.sched.tenant_layout_state["tenant-one"]
        self.assertNotEqual(old, new)

        for _ in iterate_timeout(10, "Wait for all schedulers to update"):
            layout_states = [
                a.sched.local_layout_state["tenant-one"]
                for a in self.scheds.instances
            ]
            if all(l == new for l in layout_states):
                break
