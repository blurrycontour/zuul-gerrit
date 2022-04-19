# Copyright 2022 Acme Gating, LLC
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

import json

from zuul.zk.components import ComponentRegistry

from tests.base import ZuulTestCase, simple_layout, iterate_timeout


def model_version(version):
    """Specify a model version for a model upgrade test

    This creates a dummy scheduler component with the specified model
    API version.  The component is created before any other, so it
    will appear to Zuul that it is joining an existing cluster with
    data at the old version.
    """

    def decorator(test):
        test.__model_version__ = version
        return test
    return decorator


class TestModelUpgrade(ZuulTestCase):
    tenant_config_file = "config/single-tenant/main-model-upgrade.yaml"
    scheduler_count = 1

    def getJobData(self, tenant, pipeline):
        item_path = f'/zuul/tenant/{tenant}/pipeline/{pipeline}/item'
        count = 0
        for item in self.zk_client.client.get_children(item_path):
            bs_path = f'{item_path}/{item}/buildset'
            for buildset in self.zk_client.client.get_children(bs_path):
                data = json.loads(self.getZKObject(
                    f'{bs_path}/{buildset}/job/check-job'))
                count += 1
                yield data
        if not count:
            raise Exception("No job data found")

    @model_version(0)
    @simple_layout('layouts/simple.yaml')
    def test_model_upgrade_0_1(self):
        component_registry = ComponentRegistry(self.zk_client)
        self.assertEqual(component_registry.model_api, 0)

        # Upgrade our component
        self.model_test_component_info.model_api = 1

        for _ in iterate_timeout(30, "model api to update"):
            if component_registry.model_api == 1:
                break

    @model_version(2)
    @simple_layout('layouts/pipeline-supercedes.yaml')
    def test_supercedes(self):
        """
        Test that pipeline supsercedes still work with model API 2,
        which uses deqeueue events.
        """
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.builds[0].name, 'test-job')

        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)
        self.assertEqual(self.builds[0].name, 'test-job')
        self.assertEqual(self.builds[0].pipeline, 'gate')

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 0)
        self.assertEqual(A.reported, 2)
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertHistory([
            dict(name='test-job', result='ABORTED', changes='1,1'),
            dict(name='test-job', result='SUCCESS', changes='1,1'),
        ], ordered=False)

    @model_version(4)
    def test_model_4(self):
        # Test that Zuul return values are correctly passed to child
        # jobs in version 4 compatibility mode.
        A = self.fake_gerrit.addFakeChange('org/project3', 'master', 'A')
        fake_data = [
            {'name': 'image',
             'url': 'http://example.com/image',
             'metadata': {
                 'type': 'container_image'
             }},
        ]
        self.executor_server.returnData(
            'project-merge', A,
            {'zuul': {'artifacts': fake_data}}
        )
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='project-merge', result='SUCCESS', changes='1,1'),
            dict(name='project-test1', result='SUCCESS', changes='1,1'),
            dict(name='project-test2', result='SUCCESS', changes='1,1'),
            dict(name='project1-project2-integration',
                 result='SUCCESS', changes='1,1'),
        ], ordered=False)
        # Verify that the child jobs got the data from the parent
        test1 = self.getJobFromHistory('project-test1')
        self.assertEqual(fake_data[0]['url'],
                         test1.parameters['zuul']['artifacts'][0]['url'])
        integration = self.getJobFromHistory('project1-project2-integration')
        self.assertEqual(fake_data[0]['url'],
                         integration.parameters['zuul']['artifacts'][0]['url'])

    @model_version(4)
    def test_model_4_5(self):
        # Changes share a queue, but with only one job, the first
        # merges before the second starts.
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        fake_data = [
            {'name': 'image',
             'url': 'http://example.com/image',
             'metadata': {
                 'type': 'container_image'
             }},
        ]
        self.executor_server.returnData(
            'project-merge', A,
            {'zuul': {'artifacts': fake_data}}
        )
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 1)

        # Upgrade our component
        self.model_test_component_info.model_api = 5

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name='project-merge', result='SUCCESS', changes='1,1'),
            dict(name='project-test1', result='SUCCESS', changes='1,1'),
            dict(name='project-test2', result='SUCCESS', changes='1,1'),
            dict(name='project1-project2-integration',
                 result='SUCCESS', changes='1,1'),
        ], ordered=False)
        # Verify that the child job got the data from the parent
        test1 = self.getJobFromHistory('project-test1')
        self.assertEqual(fake_data[0]['url'],
                         test1.parameters['zuul']['artifacts'][0]['url'])

    @model_version(5)
    def test_model_5_6(self):
        # This exercises the min_ltimes=None case in configloader on
        # layout updates.
        first = self.scheds.first
        second = self.createScheduler()
        second.start()
        self.assertEqual(len(self.scheds), 2)
        for _ in iterate_timeout(10, "until priming is complete"):
            state_one = first.sched.local_layout_state.get("tenant-one")
            if state_one:
                break

        for _ in iterate_timeout(
                10, "all schedulers to have the same layout state"):
            if (second.sched.local_layout_state.get(
                    "tenant-one") == state_one):
                break

        with second.sched.layout_update_lock, second.sched.run_handler_lock:
            file_dict = {'zuul.d/test.yaml': ''}
            A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A',
                                               files=file_dict)
            A.setMerged()
            self.fake_gerrit.addEvent(A.getChangeMergedEvent())
            self.waitUntilSettled(matcher=[first])

            # Delete the layout data to simulate the first scheduler
            # being on model api 5 (we write the data regardless of
            # the cluster version since it's a new znode).
            self.scheds.first.sched.zk_client.client.delete(
                '/zuul/layout-data', recursive=True)
        self.waitUntilSettled()
        self.assertEqual(first.sched.local_layout_state.get("tenant-one"),
                         second.sched.local_layout_state.get("tenant-one"))

    # No test for model version 7 (secrets in blob store): old and new
    # code paths are exercised in existing tests since small secrets
    # don't use the blob store.


class TestSemaphoreModelUpgrade(ZuulTestCase):
    tenant_config_file = 'config/semaphore/main.yaml'

    @model_version(1)
    def test_semaphore_handler_cleanup(self):
        self.executor_server.hold_jobs_in_build = True
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        semaphore_holders = tenant.semaphore_handler.semaphoreHolders(
            "test-semaphore")
        self.log.debug("Semaphore holders: %s", repr(semaphore_holders))
        self.assertEqual(len(semaphore_holders), 1)
        # Assert that we are still using the old-style handler format
        self.assertTrue(all(isinstance(h, str) for h in semaphore_holders))

        # Save some variables for later use while the job is running
        check_pipeline = tenant.layout.pipelines['check']
        item = check_pipeline.getAllItems()[0]
        job = item.getJob('semaphore-one-test1')

        tenant.semaphore_handler.cleanupLeaks()
        # Nothing has leaked; our handle should be present.
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            1)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # Make sure the semaphore is released normally
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)

        # Use our previously saved data to simulate a leaked semaphore
        # with the OLD handler format.
        tenant.semaphore_handler.acquire(item, job, False)
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            1)

        tenant.semaphore_handler.cleanupLeaks()
        # Make sure the semaphore is NOT cleaned up as the model version
        # is still < 2
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            1)

        # Upgrade our component
        self.model_test_component_info.model_api = 2

        # Wait for it to propagate
        for _ in iterate_timeout(30, "model api to update"):
            if self.scheds.first.sched.component_registry.model_api == 2:
                break

        tenant.semaphore_handler.cleanupLeaks()
        # Make sure we are not touching old-style handlers during cleanup.
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            1)

        # Try to release the old-style semaphore after the model API upgrade.
        tenant.semaphore_handler.release(self.scheds.first.sched, item, job)
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)

        # Use our previously saved data to simulate a leaked semaphore
        # with the NEW handler format.
        tenant.semaphore_handler.acquire(item, job, False)
        semaphore_holders = tenant.semaphore_handler.semaphoreHolders(
            "test-semaphore")
        self.log.debug("Semaphore holders: %s", repr(semaphore_holders))
        self.assertEqual(len(semaphore_holders), 1)
        # Assert that we are now using the new-style handler format
        self.assertTrue(all(isinstance(h, dict) for h in semaphore_holders))

        tenant.semaphore_handler.cleanupLeaks()
        # Make sure the leaked semaphore is cleaned up
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)


class TestGithubModelUpgrade(ZuulTestCase):
    config_file = 'zuul-github-driver.conf'
    scheduler_count = 1

    @model_version(3)
    @simple_layout('layouts/gate-github.yaml', driver='github')
    def test_status_checks_removal(self):
        # This tests the old behavior -- that changes are not dequeued
        # once their required status checks are removed -- since the
        # new behavior requires a flag in ZK.
        # Contrast with test_status_checks_removal.
        github = self.fake_github.getGithubClient()
        repo = github.repo_from_project('org/project')
        repo._set_branch_protection(
            'master', contexts=['something/check', 'tenant-one/gate'])

        A = self.fake_github.openFakePullRequest('org/project', 'master', 'A')
        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = True
        # Since the required status 'something/check' is not fulfilled,
        # no job is expected
        self.assertEqual(0, len(self.history))

        # Set the required status 'something/check'
        repo.create_status(A.head_sha, 'success', 'example.com', 'description',
                           'something/check')

        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        # Remove it and verify the change is not dequeued (old behavior).
        repo.create_status(A.head_sha, 'failed', 'example.com', 'description',
                           'something/check')
        self.fake_github.emitEvent(A.getCommitStatusEvent('something/check',
                                                          state='failed',
                                                          user='foo'))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # the change should have entered the gate
        self.assertHistory([
            dict(name='project-test1', result='SUCCESS'),
            dict(name='project-test2', result='SUCCESS'),
        ], ordered=False)
        self.assertTrue(A.is_merged)
