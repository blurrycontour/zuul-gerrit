# Copyright 2021 BMW Group
# Copyright 2021 Acme Gating, LLC
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

import zuul.model

from tests.base import iterate_timeout, ZuulTestCase, simple_layout


class TestScaleOutScheduler(ZuulTestCase):
    tenant_config_file = "config/single-tenant/main.yaml"
    # Those tests are testing specific interactions between multiple
    # schedulers. They create additional schedulers as necessary and
    # start or stop them individually to test specific interactions.
    # Using the scheduler_count in addition to create even more
    # schedulers doesn't make sense for those tests.
    scheduler_count = 1

    def test_multi_scheduler(self):
        # A smoke test that we can enqueue a change with one scheduler
        # and have another one finish the run.
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        app = self.createScheduler()
        app.start()
        self.assertEqual(len(self.scheds), 2)

        # Hold the lock on the first scheduler so that only the second
        # will act.
        with self.scheds.first.sched.run_handler_lock:
            self.executor_server.hold_jobs_in_build = False
            self.executor_server.release()
            self.waitUntilSettled(matcher=[app])

        self.assertHistory([
            dict(name='project-merge', result='SUCCESS', changes='1,1'),
            dict(name='project-test1', result='SUCCESS', changes='1,1'),
            dict(name='project-test2', result='SUCCESS', changes='1,1'),
        ], ordered=False)

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
        self.assertIsNotNone(
            first_app.sched.merger.merger_api.history.get("cat"))
        self.assertIsNone(
            second_app.sched.merger.merger_api.history.get("cat"))

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

    def test_pipeline_summary(self):
        # Test that we can deal with a truncated pipeline summary
        self.executor_server.hold_jobs_in_build = True
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        pipeline = tenant.layout.pipelines['check']
        context = self.createZKContext()

        def new_summary():
            summary = zuul.model.PipelineSummary()
            summary._set(pipeline=pipeline)
            summary.refresh(context)
            return summary

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Check we have a good summary
        summary1 = new_summary()
        self.assertNotEqual(summary1.status, {})
        self.assertTrue(context.client.exists(summary1.getPath()))

        # Make a syntax error in the status summary json
        summary = new_summary()
        summary._save(context, b'{"foo')

        # With the corrupt data, we should get an empty status but the
        # path should still exist.
        summary2 = new_summary()
        self.assertEqual(summary2.status, {})
        self.assertTrue(context.client.exists(summary2.getPath()))

        # Our earlier summary object should use its cached data
        summary1.refresh(context)
        self.assertNotEqual(summary1.status, {})

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # The scheduler should have written a new summary that our
        # second object can read now.
        summary2.refresh(context)
        self.assertNotEqual(summary2.status, {})

    @simple_layout('layouts/semaphore.yaml')
    def test_semaphore(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.builds[0].name, 'test1')
        self.assertHistory([])

        tenant = self.scheds.first.sched.abide.tenants['tenant-one']
        semaphore = tenant.semaphore_handler.getSemaphores()[0]
        holders = tenant.semaphore_handler.semaphoreHolders(semaphore)
        self.assertEqual(len(holders), 1)

        # Start a second scheduler so that it runs through the initial
        # cleanup processes.
        app = self.createScheduler()
        # Hold the lock on the second scheduler so that if any events
        # happen, they are processed by the first scheduler (this lets
        # them be as out of sync as possible).
        with app.sched.run_handler_lock:
            app.start()
            self.assertEqual(len(self.scheds), 2)
            self.waitUntilSettled(matcher=[self.scheds.first])
            # Wait until initial cleanup is run
            app.sched.start_cleanup_thread.join()
            # We should not have released the semaphore
            holders = tenant.semaphore_handler.semaphoreHolders(semaphore)
            self.assertEqual(len(holders), 1)

        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.builds[0].name, 'test2')
        self.assertHistory([
            dict(name='test1', result='SUCCESS', changes='1,1'),
        ], ordered=False)
        holders = tenant.semaphore_handler.semaphoreHolders(semaphore)
        self.assertEqual(len(holders), 1)

        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(len(self.builds), 0)
        self.assertHistory([
            dict(name='test1', result='SUCCESS', changes='1,1'),
            dict(name='test2', result='SUCCESS', changes='1,1'),
        ], ordered=False)

        holders = tenant.semaphore_handler.semaphoreHolders(semaphore)
        self.assertEqual(len(holders), 0)
