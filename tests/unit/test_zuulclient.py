# Copyright 2020 Red Hat, inc.
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

import os
import time
import jwt
import sys
import subprocess

import zuul.web
import zuul.rpcclient

from tests.base import iterate_timeout
from tests.unit.test_web import BaseTestWeb


class TestZuulClient(BaseTestWeb):
    config_file = 'zuul-admin-web.conf'

    def test_autohold(self):
        """Test that autohold can be set with the Web client"""
        authz = {'iss': 'zuul_operator',
                 'aud': 'zuul.example.com',
                 'sub': 'testuser',
                 'zuul': {
                     'admin': ['tenant-one', ]
                 },
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul-client'),
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'autohold', '--reason', 'some reason',
             '--tenant', 'tenant-one', '--project', 'org/project',
             '--job', 'project-test2', '--count', '1'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output[0])
        # Check result in rpc client
        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        autohold_requests = client.autohold_list()
        self.assertNotEqual([], autohold_requests)
        self.assertEqual(1, len(autohold_requests))
        request = autohold_requests[0]
        self.assertEqual('tenant-one', request['tenant'])
        self.assertIn('org/project', request['project'])
        self.assertEqual('project-test2', request['job'])
        self.assertEqual(".*", request['ref_filter'])
        self.assertEqual("some reason", request['reason'])
        self.assertEqual(1, request['max_count'])

    def test_enqueue(self):
        """Test that the Web client can enqueue a change"""
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        A.addApproval('Approved', 1)

        authz = {'iss': 'zuul_operator',
                 'aud': 'zuul.example.com',
                 'sub': 'testuser',
                 'zuul': {
                     'admin': ['tenant-one', ]
                 },
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul-client'),
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'enqueue', '--tenant', 'tenant-one',
             '--project', 'org/project',
             '--pipeline', 'gate', '--change', '1,1'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
        self.waitUntilSettled()

    def test_enqueue_ref(self):
        """Test that the Web client can enqueue a ref"""
        p = "review.example.com/org/project"
        upstream = self.getUpstreamRepos([p])
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.setMerged()
        A_commit = str(upstream[p].commit('master'))
        self.log.debug("A commit: %s" % A_commit)

        authz = {'iss': 'zuul_operator',
                 'aud': 'zuul.example.com',
                 'sub': 'testuser',
                 'zuul': {
                     'admin': ['tenant-one', ]
                 },
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul-client'),
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'enqueue-ref', '--tenant', 'tenant-one',
             '--project', 'org/project',
             '--pipeline', 'post', '--ref', 'master',
             '--oldrev', '90f173846e3af9154517b88543ffbd1691f31366',
             '--newrev', A_commit],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
        self.waitUntilSettled()

    def test_dequeue(self):
        """Test that the Web client can dequeue a change"""
        start_builds = len(self.builds)
        self.create_branch('org/project', 'stable')
        self.executor_server.hold_jobs_in_build = True
        self.commitConfigUpdate('common-config', 'layouts/timer.yaml')
        self.scheds.execute(lambda app: app.sched.reconfigure(app.config))
        self.waitUntilSettled()

        for _ in iterate_timeout(30, 'Wait for a build on hold'):
            if len(self.builds) > start_builds:
                break
        self.waitUntilSettled()

        authz = {'iss': 'zuul_operator',
                 'aud': 'zuul.example.com',
                 'sub': 'testuser',
                 'zuul': {
                     'admin': ['tenant-one', ]
                 },
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul-client'),
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'dequeue', '--tenant', 'tenant-one', '--project', 'org/project',
             '--pipeline', 'periodic', '--ref', 'refs/heads/stable'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
        self.waitUntilSettled()

        self.commitConfigUpdate('common-config',
                                'layouts/no-timer.yaml')
        self.scheds.execute(lambda app: app.sched.reconfigure(app.config))
        self.waitUntilSettled()
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(self.countJobResults(self.history, 'ABORTED'), 1)

    def test_promote(self):
        "Test that the Web client can promote a change"
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')
        C = self.fake_gerrit.addFakeChange('org/project', 'master', 'C')
        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)
        C.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(C.addApproval('Approved', 1))

        self.waitUntilSettled()

        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        items = tenant.layout.pipelines['gate'].getAllItems()
        enqueue_times = {}
        for item in items:
            enqueue_times[str(item.change)] = item.enqueue_time

        # Promote B and C using the cli
        authz = {'iss': 'zuul_operator',
                 'aud': 'zuul.example.com',
                 'sub': 'testuser',
                 'zuul': {
                     'admin': ['tenant-one', ]
                 },
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul-client'),
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'promote', '--tenant', 'tenant-one',
             '--pipeline', 'gate', '--changes', '2,1', '3,1'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
        self.waitUntilSettled()

        # ensure that enqueue times are durable
        items = tenant.layout.pipelines['gate'].getAllItems()
        for item in items:
            self.assertEqual(
                enqueue_times[str(item.change)], item.enqueue_time)

        self.waitUntilSettled()
        self.executor_server.release('.*-merge')
        self.waitUntilSettled()
        self.executor_server.release('.*-merge')
        self.waitUntilSettled()
        self.executor_server.release('.*-merge')
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 6)
        self.assertEqual(self.builds[0].name, 'project-test1')
        self.assertEqual(self.builds[1].name, 'project-test2')
        self.assertEqual(self.builds[2].name, 'project-test1')
        self.assertEqual(self.builds[3].name, 'project-test2')
        self.assertEqual(self.builds[4].name, 'project-test1')
        self.assertEqual(self.builds[5].name, 'project-test2')

        self.assertTrue(self.builds[0].hasChanges(B))
        self.assertFalse(self.builds[0].hasChanges(A))
        self.assertFalse(self.builds[0].hasChanges(C))

        self.assertTrue(self.builds[2].hasChanges(B))
        self.assertTrue(self.builds[2].hasChanges(C))
        self.assertFalse(self.builds[2].hasChanges(A))

        self.assertTrue(self.builds[4].hasChanges(B))
        self.assertTrue(self.builds[4].hasChanges(C))
        self.assertTrue(self.builds[4].hasChanges(A))

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2)
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.data['status'], 'MERGED')
        self.assertEqual(C.reported, 2)
