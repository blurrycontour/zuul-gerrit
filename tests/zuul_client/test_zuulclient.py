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

import configparser
import io
import time
import jwt
import os
import subprocess
import tempfile
import textwrap

from zuul.lib import encryption
import zuul.web
import zuul.rpcclient

from tests.base import iterate_timeout
from tests.unit.test_web import BaseTestWeb
from tests.base import FIXTURE_DIR


class TestSmokeZuulClient(BaseTestWeb):
    def test_is_installed(self):
        """Test that the CLI is installed"""
        test_version = subprocess.check_output(
            ['zuul-client', '--version'],
            stderr=subprocess.STDOUT)
        self.assertTrue(b'Zuul-client version:' in test_version)


class TestZuulClientAuthToken(BaseTestWeb):
    """Test the auth token creation workflow"""
    config_file = 'zuul-admin-web.conf'

    def test_no_authenticator(self):
        """Test that token generation is not possible without authenticator"""
        p = subprocess.Popen(
            ['zuul-client',
             '-c', os.path.join(FIXTURE_DIR, self.config_file),
             'create-auth-token',
             '--auth-config', 'not_zuul_operator',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one', ],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 1, 'The command must exit 1')

    def test_unsupported_driver(self):
        """Test that token generation is not possible with wrong driver"""
        old_conf = io.StringIO()
        self.config.write(old_conf)
        self.config.add_section('auth someauth')
        self.config.set('auth someauth', 'driver', 'OpenIDConnect')
        with open(os.path.join(self.test_root, 'OIDC.conf'), 'w') as f:
            self.config.write(f)
        p = subprocess.Popen(
            ['zuul-client',
             '-c', os.path.join(self.test_root, 'OIDC.conf'),
             'create-auth-token',
             '--auth-config', 'someauth',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one', ],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        old_conf.seek(0)
        self.config = configparser.ConfigParser()
        self.config.read_file(old_conf)
        self.assertEqual(p.returncode, 1, 'The command must exit 1')

    def _test_api_with_token(self, bearer_token, tenant):
        req = self.get_url('/api/user/authorizations',
                           headers={'Authorization': bearer_token})
        data = req.json()
        self.assertTrue('zuul' in data, data)
        self.assertTrue('admin' in data['zuul'], data)
        self.assertTrue(data['zuul']['admin'], data)
        self.assertTrue(tenant in data['zuul']['scope'], data)

    def test_token_generation_HS256(self):
        """Test token generation and use with HS256"""
        p = subprocess.Popen(
            ['zuul-client',
             '-c', os.path.join(FIXTURE_DIR, self.config_file),
             'create-auth-token',
             '--auth-conf', 'zuul_operator',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one', ],
            stdout=subprocess.PIPE)
        now = time.time()
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        self.assertTrue(out.startswith(b"Bearer "), out)
        # there is a trailing carriage return in the output
        token = jwt.decode(out[len("Bearer "):-1],
                           key=self.config.get(
                               'auth zuul_operator',
                               'secret'),
                           algorithms=[self.config.get(
                               'auth zuul_operator',
                               'driver')],
                           audience=self.config.get(
                               'auth zuul_operator',
                               'client_id'),)
        self.assertEqual('marshmallow_man', token.get('sub'))
        self.assertEqual('zuul_operator', token.get('iss'))
        self.assertEqual('zuul.example.com', token.get('aud'))
        admin_tenants = token.get('zuul', {}).get('admin', [])
        self.assertTrue('tenant_one' in admin_tenants, admin_tenants)
        # allow one minute for the process to run
        self.assertTrue(580 <= int(token['exp']) - now < 660,
                        (token['exp'], now))
        self._test_api_with_token(out, 'tenant_one')

    def test_token_generation_RS256(self):
        """Test token generation and use with RS256"""
        private, public = encryption.generate_rsa_keypair()
        public_pem = encryption.serialize_rsa_public_key(public)
        public_file = tempfile.NamedTemporaryFile(delete=False)
        public_file.write(public_pem)
        public_file.close()
        private_pem = encryption.serialize_rsa_private_key(private)
        private_file = tempfile.NamedTemporaryFile(delete=False)
        private_file.write(private_pem)
        private_file.close()

        old_conf = io.StringIO()
        self.config.write(old_conf)
        self.config.set(
            'auth zuul_operator_2', 'public_key', public_file.name)
        self.config.set(
            'auth zuul_operator_2', 'private_key', private_file.name)
        temp_conf = tempfile.NamedTemporaryFile(delete=False)
        self.config.write(temp_conf)

        p = subprocess.Popen(
            ['zuul-client',
             '-c', temp_conf.name,
             'create-auth-token',
             '--auth-conf', 'zuul_operator_2',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one', ],
            stdout=subprocess.PIPE)
        now = time.time()
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        self.assertTrue(out.startswith(b"Bearer "), out)
        # there is a trailing carriage return in the output
        token = jwt.decode(out[len("Bearer "):-1],
                           key=public_pem,
                           algorithms=[self.config.get(
                               'auth zuul_operator_2',
                               'driver')],
                           audience=self.config.get(
                               'auth zuul_operator',
                               'client_id'),)
        self.assertEqual('marshmallow_man', token.get('sub'))
        self.assertEqual('zuul_operator', token.get('iss'))
        self.assertEqual('zuul.example.com', token.get('aud'))
        admin_tenants = token.get('zuul', {}).get('admin', [])
        self.assertTrue('tenant_one' in admin_tenants, admin_tenants)
        # allow one minute for the process to run
        self.assertTrue(580 <= int(token['exp']) - now < 660,
                        (token['exp'], now))
        self._test_api_with_token(out, 'tenant_one')
        # clean up
        os.unlink(private_file.name)
        os.unlink(public_file.name)
        old_conf.seek(0)
        self.config = configparser.ConfigParser()
        self.config.read_file(old_conf)
        os.unlink(temp_conf.name)


class TestZuulClientEncrypt(BaseTestWeb):
    """Test using zuul-client to encrypt secrets"""
    tenant_config_file = 'config/secrets/main.yaml'
    config_file = 'zuul-admin-web.conf'
    secret = {'password': 'zuul-client'}

    def setUp(self):
        super(TestZuulClientEncrypt, self).setUp()
        self.executor_server.hold_jobs_in_build = False

    def _getSecrets(self, job, pbtype):
        secrets = []
        build = self.getJobFromHistory(job)
        for pb in build.parameters[pbtype]:
            secrets.append(pb['secrets'])
        return secrets

    def test_encrypt(self):
        """Test that we can use zuul-client to generate a project secret"""
        p = subprocess.Popen(
            ['zuul-client',
             '--zuul-url', self.base_url,
             'encrypt', '--tenant', 'tenant-one', '--project', 'org/project2',
             '--secret-name', 'my_secret', '--field-name', 'password'],
            stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        p.stdin.write(
            str.encode(self.secret['password'])
        )
        output, error = p.communicate()
        p.stdin.close()
        self._test_encrypt(output, error)

    def test_encrypt_outfile(self):
        """Test that we can use zuul-client to generate a project secret to a
        file"""
        outfile = tempfile.NamedTemporaryFile(delete=False)
        p = subprocess.Popen(
            ['zuul-client',
             '--zuul-url', self.base_url,
             'encrypt', '--tenant', 'tenant-one', '--project', 'org/project2',
             '--secret-name', 'my_secret', '--field-name', 'password',
             '--outfile', outfile.name],
            stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        p.stdin.write(
            str.encode(self.secret['password'])
        )
        _, error = p.communicate()
        p.stdin.close()
        output = outfile.read()
        self._test_encrypt(output, error)

    def test_encrypt_infile(self):
        """Test that we can use zuul-client to generate a project secret from
        a file"""
        infile = tempfile.NamedTemporaryFile(delete=False)
        infile.write(
            str.encode(self.secret['password'])
        )
        infile.close()
        p = subprocess.Popen(
            ['zuul-client',
             '--zuul-url', self.base_url,
             'encrypt', '--tenant', 'tenant-one', '--project', 'org/project2',
             '--secret-name', 'my_secret', '--field-name', 'password',
             '--infile', infile.name],
            stdout=subprocess.PIPE)
        output, error = p.communicate()
        os.unlink(infile.name)
        self._test_encrypt(output, error)

    def _test_encrypt(self, output, error):
        self.assertEqual(None, error, error)
        self.assertTrue(b'- secret:' in output, output.decode())
        new_repo_conf = output.decode()
        new_repo_conf += textwrap.dedent(
            """

            - job:
                parent: base
                name: project2-secret
                run: playbooks/secret.yaml
                secrets:
                  - my_secret

            - project:
                check:
                  jobs:
                    - project2-secret
                gate:
                  jobs:
                    - noop
            """
        )
        file_dict = {'zuul.yaml': new_repo_conf}
        A = self.fake_gerrit.addFakeChange('org/project2', 'master',
                                           'Add secret',
                                           files=file_dict)
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()
        self.assertEqual(A.data['status'], 'MERGED')
        self.fake_gerrit.addEvent(A.getChangeMergedEvent())
        self.waitUntilSettled()
        # check that the secret is used from there on
        B = self.fake_gerrit.addFakeChange('org/project2', 'master',
                                           'test secret',
                                           files={'newfile': 'xxx'})
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.assertEqual(B.reported, 1, "B should report success")
        self.assertHistory([
            dict(name='project2-secret', result='SUCCESS', changes='2,1'),
        ])
        secrets = self._getSecrets('project2-secret', 'playbooks')
        self.assertEqual(
            secrets,
            [{'my_secret': self.secret}],
            secrets)


class TestZuulClientAdmin(BaseTestWeb):
    """Test the admin commands of zuul-client"""
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
            ['zuul-client',
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'autohold', '--reason', 'some reason',
             '--tenant', 'tenant-one', '--project', 'org/project',
             '--job', 'project-test2', '--count', '1'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
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
        self.executor_server.hold_jobs_in_build = True
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
            ['zuul-client',
             '--zuul-url', self.base_url, '--auth-token', token, '-v',
             'enqueue', '--tenant', 'tenant-one',
             '--project', 'org/project',
             '--pipeline', 'gate', '--change', '1,1'],
            stdout=subprocess.PIPE)
        output = p.communicate()
        self.assertEqual(p.returncode, 0, output)
        self.waitUntilSettled()
        # Check the build history for our enqueued build
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        # project-merge, project-test1, project-test2 in SUCCESS
        self.assertEqual(self.countJobResults(self.history, 'SUCCESS'), 3)

    def test_enqueue_ref(self):
        """Test that the Web client can enqueue a ref"""
        self.executor_server.hold_jobs_in_build = True
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
            ['zuul-client',
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
        # Check the build history for our enqueued build
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(self.countJobResults(self.history, 'SUCCESS'), 1)

    def test_dequeue(self):
        """Test that the Web client can dequeue a change"""
        self.executor_server.hold_jobs_in_build = True
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
            ['zuul-client',
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
            ['zuul-client',
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
