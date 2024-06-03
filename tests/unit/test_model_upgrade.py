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

from zuul.zk.components import (
    COMPONENT_REGISTRY,
    ComponentRegistry,
    SchedulerComponent,
)
from tests.base import (
    BaseTestCase,
    ZuulTestCase,
    simple_layout,
    iterate_timeout,
)
from zuul.zk import ZooKeeperClient
from zuul.zk.branch_cache import BranchCache, BranchFlag
from zuul.zk.zkobject import ZKContext
from tests.unit.test_zk import DummyConnection


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


class TestBranchCacheUpgrade(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()
        self.model_test_component_info = SchedulerComponent(
            self.zk_client, 'test_component')
        self.model_test_component_info.register(26)
        self.component_registry = ComponentRegistry(self.zk_client)
        COMPONENT_REGISTRY.create(self.zk_client)

    def test_branch_cache_upgrade(self):
        conn = DummyConnection()
        cache = BranchCache(self.zk_client, conn, self.component_registry)

        # Test all of the different combinations of old branch cache data:

        # project0: failed both queries
        # project1: protected and queried both
        # project2: protected and only queried unprotected
        # project3: protected and only queried protected
        # project4: unprotected and queried both
        # project5: unprotected and only queried unprotected
        # project6: unprotected and only queried protected
        # project7: both and queried both
        # project8: both and only queried unprotected
        # project9: both and only queried protected

        data = {
            'default_branch': {},
            'merge_modes': {},
            'protected': {
                'project0': None,
                'project1': ['protected_branch'],
                # 'project2':
                'project3': ['protected_branch'],
                'project4': [],
                # 'project5':
                'project6': [],
                'project7': ['protected_branch'],
                # 'project8':
                'project9': ['protected_branch'],
            },
            'remainder': {
                'project0': None,
                'project1': [],
                'project2': ['protected_branch'],
                # 'project3':
                'project4': ['unprotected_branch'],
                'project5': ['unprotected_branch'],
                # 'project6':
                'project7': ['unprotected_branch'],
                'project8': ['protected_branch', 'unprotected_branch'],
                # 'project9':
            }
        }
        ctx = ZKContext(self.zk_client, None, None, self.log)
        data = json.dumps(data, sort_keys=True).encode("utf8")
        cache.cache._save(ctx, data)
        cache.cache.refresh(ctx)

        expected = {
            'project0': {
                'completed': BranchFlag.CLEAR,
                'failed': BranchFlag.PROTECTED | BranchFlag.PRESENT,
                'branches': {}
            },
            'project1': {
                'completed': BranchFlag.PROTECTED | BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'protected': True},
                }
            },
            'project2': {
                'completed': BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'present': True},
                }
            },
            'project3': {
                'completed': BranchFlag.PROTECTED,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'protected': True},
                }
            },
            'project4': {
                'completed': BranchFlag.PROTECTED | BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'unprotected_branch': {'present': True},
                }
            },
            'project5': {
                'completed': BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'unprotected_branch': {'present': True},
                }
            },
            'project6': {
                'completed': BranchFlag.PROTECTED,
                'failed': BranchFlag.CLEAR,
                'branches': {}
            },
            'project7': {
                'completed': BranchFlag.PROTECTED | BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'protected': True},
                    'unprotected_branch': {'present': True},
                }
            },
            'project8': {
                'completed': BranchFlag.PRESENT,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'present': True},
                    'unprotected_branch': {'present': True},
                }
            },
            'project9': {
                'completed': BranchFlag.PROTECTED,
                'failed': BranchFlag.CLEAR,
                'branches': {
                    'protected_branch': {'protected': True},
                }
            },
        }

        for project_name, project in expected.items():
            cache_project = cache.cache.projects[project_name]
            self.assertEqual(
                project['completed'],
                cache_project.completed_flags,
            )
            self.assertEqual(
                project['failed'],
                cache_project.failed_flags,
            )
            for branch_name, branch in project['branches'].items():
                cache_branch = cache_project.branches[branch_name]
                self.assertEqual(
                    branch.get('protected'),
                    cache_branch.protected,
                )
                self.assertEqual(
                    branch.get('present'),
                    cache_branch.present,
                )
            for branch_name in cache_project.branches.keys():
                if branch_name not in project['branches']:
                    raise Exception(f"Unexpected branch {branch_name}")
