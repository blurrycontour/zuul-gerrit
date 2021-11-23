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

from zuul.model import MergeRequest

from tests.base import iterate_timeout, ZuulTestCase


class TestScaleOutScheduler(ZuulTestCase):
    tenant_config_file = "config/single-tenant/main.yaml"
    # Those tests are testing specific interactions between multiple
    # schedulers. They create additional schedulers as necessary and
    # start or stop them individually to test specific interactions.
    # Using the scheduler_count in addition to create even more
    # schedulers doesn't make sense for those tests.
    scheduler_count = 1

    def test_config_priming(self):
        # Wait until scheduler is primed
        self.waitUntilSettled()
        first_app = self.scheds.first
        initial_max_hold_exp = first_app.sched.globals.max_hold_expiration
        layout_state = first_app.sched.tenant_layout_state.get("tenant-one")
        self.assertIsNotNone(layout_state)

        # Second scheduler instance
        second_app = self.createScheduler()
        # Change a system attribute in order to check that the system config
        # from Zookeeper was used.
        second_app.sched.globals.max_hold_expiration += 1234
        second_app.config.set("scheduler", "max_hold_expiration", str(
            second_app.sched.globals.max_hold_expiration))

        second_app.start()
        self.waitUntilSettled()

        self.assertEqual(first_app.sched.local_layout_state.get("tenant-one"),
                         second_app.sched.local_layout_state.get("tenant-one"))

        # Make sure only the first schedulers issued cat jobs
        first_app_cat_jobs = [
            job for job in first_app.sched.merger.merger_api.history.values()
            if job.job_type == MergeRequest.CAT]
        second_app_cat_jobs = [
            job for job in second_app.sched.merger.merger_api.history.values()
            if job.job_type == MergeRequest.CAT]
        self.assertGreater(len(first_app_cat_jobs), 0)
        self.assertEqual(len(second_app_cat_jobs), 0)

        for _ in iterate_timeout(
                10, "Wait for all schedulers to have the same system config"):
            if (first_app.sched.unparsed_abide.ltime
                    == second_app.sched.unparsed_abide.ltime):
                break

        # TODO (swestphahl): change this to assertEqual() when we remove
        # the smart reconfiguration during config priming.
        # Currently the smart reconfiguration during priming of the second
        # scheduler will update the system config in Zookeeper and the first
        # scheduler updates it's config in return.
        self.assertNotEqual(second_app.sched.globals.max_hold_expiration,
                            initial_max_hold_exp)

    def test_reconfigure(self):
        # Create a second scheduler instance
        app = self.createScheduler()
        app.start()
        self.assertEqual(len(self.scheds), 2)

        for _ in iterate_timeout(10, "Wait until priming is complete"):
            old = self.scheds.first.sched.tenant_layout_state.get("tenant-one")
            if old is not None:
                break

        for _ in iterate_timeout(
                10, "Wait for all schedulers to have the same layout state"):
            layout_states = [a.sched.local_layout_state.get("tenant-one")
                             for a in self.scheds.instances]
            if all(l == old for l in layout_states):
                break

        self.scheds.first.sched.reconfigure(self.scheds.first.config)
        self.waitUntilSettled()

        new = self.scheds.first.sched.tenant_layout_state["tenant-one"]
        self.assertNotEqual(old, new)

        for _ in iterate_timeout(10, "Wait for all schedulers to update"):
            layout_states = [a.sched.local_layout_state.get("tenant-one")
                             for a in self.scheds.instances]
            if all(l == new for l in layout_states):
                break

        layout_uuids = [a.sched.abide.tenants["tenant-one"].layout.uuid
                        for a in self.scheds.instances]
        self.assertTrue(all(l == new.uuid for l in layout_uuids))
        self.waitUntilSettled()

    def test_change_cache(self):
        # Test re-using a change from the change cache.
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')

        B.setDependsOn(A, 1)

        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        # This has populated the change cache with our change.

        app = self.createScheduler()
        app.start()
        self.assertEqual(len(self.scheds), 2)

        # Hold the lock on the first scheduler so that only the second
        # will act.
        with self.scheds.first.sched.run_handler_lock:
            # Enqueue the change again.  The second scheduler will
            # load the change object from the cache.
            self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))

            self.waitUntilSettled(matcher=[app])

        # Each job should appear twice and contain both changes.
        self.assertHistory([
            dict(name='project-merge', result='SUCCESS', changes='1,1 2,1'),
            dict(name='project-test1', result='SUCCESS', changes='1,1 2,1'),
            dict(name='project-test2', result='SUCCESS', changes='1,1 2,1'),
            dict(name='project-merge', result='SUCCESS', changes='1,1 2,1'),
            dict(name='project-test1', result='SUCCESS', changes='1,1 2,1'),
            dict(name='project-test2', result='SUCCESS', changes='1,1 2,1'),
        ], ordered=False)
