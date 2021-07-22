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

from tests.base import iterate_timeout, ZuulTestCase


class TestScaleOutScheduler(ZuulTestCase):
    tenant_config_file = "config/single-tenant/main.yaml"

    def create_scheduler(self):
        return self.scheds.create(
            self.log,
            self.config,
            self.changes,
            self.additional_event_queues,
            self.upstream_root,
            self.rpcclient,
            self.poller_events,
            self.git_url_with_auth,
            self.source_only,
            self.fake_sql,
            self.addCleanup,
            self.validate_tenants)

    def test_config_priming(self):
        for _ in iterate_timeout(10, "Wait until priming is complete"):
            layout_state = self.scheds.first.sched.tenant_layout_state.get(
                "tenant-one")
            if layout_state is not None:
                break

        # Second scheduler instance
        app = self.create_scheduler()
        # Change a system attribute in order to check that the system config
        # from Zookeeper was used.
        app.sched.max_hold += 1234
        app.config.set("scheduler", "max_hold_expiration",
                       str(app.sched.max_hold))
        app.start()

        self.assertEqual(len(self.scheds), 2)
        for _ in iterate_timeout(
                10, "Wait for all schedulers to have the same layout state"):
            tenants = [s.sched.unparsed_abide.tenants
                       for s in self.scheds.instances]
            if all(tenants):
                break

        self.assertEqual(self.scheds.first.sched.max_hold, app.sched.max_hold)
