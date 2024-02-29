# Copyright 2022, 2024 Acme Gating, LLC
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

from tests.base import (
    ZuulTestCase,
    simple_layout,
    iterate_timeout,
)


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


class TestGithubModelUpgrade(ZuulTestCase):
    config_file = "zuul-gerrit-github.conf"
    scheduler_count = 1

    @model_version(26)
    @simple_layout('layouts/gate-github.yaml', driver='github')
    def test_model_26(self):
        # This excercises the backwards-compat branch cache
        # serialization code; no uprade happens in this test.
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

        conn = first.connections.connections['github']
        with self.createZKContext() as ctx:
            # There's a lot of exception catching in the branch cache,
            # so exercise a serialize/deserialize cycle.
            old = conn._branch_cache.cache.serialize(ctx)
            data = json.loads(old)
            self.assertEqual(['master'],
                             data['remainder']['org/common-config'])
            new = conn._branch_cache.cache.deserialize(old, ctx)
            self.assertTrue(new['projects'][
                'org/common-config'].branches['master'].present)

        with first.sched.layout_update_lock, first.sched.run_handler_lock:
            A = self.fake_github.openFakePullRequest(
                'org/project', 'master', 'A')
            self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
            self.waitUntilSettled(matcher=[second])

        self.waitUntilSettled()
        self.assertHistory([
            dict(name='project-test1', result='SUCCESS'),
            dict(name='project-test2', result='SUCCESS'),
        ], ordered=False)

    @model_version(26)
    @simple_layout('layouts/gate-github.yaml', driver='github')
    def test_model_26_27(self):
        # This excercises the branch cache upgrade.
        first = self.scheds.first
        self.model_test_component_info.model_api = 27
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

        with first.sched.layout_update_lock, first.sched.run_handler_lock:
            A = self.fake_github.openFakePullRequest(
                'org/project', 'master', 'A')
            self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
            self.waitUntilSettled(matcher=[second])

        self.waitUntilSettled()
        self.assertHistory([
            dict(name='project-test1', result='SUCCESS'),
            dict(name='project-test2', result='SUCCESS'),
        ], ordered=False)
