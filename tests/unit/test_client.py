# Copyright 2018 Red Hat, Inc.
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

import io
import os
import sys
import subprocess
import time

import configparser
import fixtures
import jwt

from tests.base import BaseTestCase
from tests.base import FIXTURE_DIR


class BaseClientTestCase(BaseTestCase):
    config_file = 'zuul.conf'

    def setUp(self):
        super(BaseClientTestCase, self).setUp()
        self.test_root = self.useFixture(fixtures.TempDir(
            rootdir=os.environ.get("ZUUL_TEST_ROOT"))).path
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(FIXTURE_DIR, self.config_file))


class TestTenantValidationClient(BaseClientTestCase):
    def test_client_tenant_conf_check(self):

        self.config.set(
            'scheduler', 'tenant_config',
            os.path.join(FIXTURE_DIR, 'config/tenant-parser/simple.yaml'))
        self.config.write(
            open(os.path.join(self.test_root, 'tenant_ok.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'tenant_ok.conf'),
             'tenant-conf-check'], stdout=subprocess.PIPE)
        p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')

        self.config.set(
            'scheduler', 'tenant_config',
            os.path.join(FIXTURE_DIR, 'config/tenant-parser/invalid.yaml'))
        self.config.write(
            open(os.path.join(self.test_root, 'tenant_ko.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'tenant_ko.conf'),
             'tenant-conf-check'], stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 1, "The command must exit 1")
        self.assertIn(
            b"expected a dictionary for dictionary", out,
            "Expected error message not found")


class TestWebTokenClient(BaseClientTestCase):
    config_file = 'zuul-admin-web.conf'

    def test_no_zuul_operator(self):
        """Test that token generation is not possible without authenticator"""
        old_conf = io.StringIO()
        self.config.write(old_conf)
        self.config.remove_section('auth zuul_operator')
        self.config.write(
            open(os.path.join(self.test_root, 'no_zuul_operator.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'no_zuul_operator.conf'),
             'create-auth-token',
             '--user', 'marshmallow_man',
             '--action', 'autohold',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        old_conf.seek(0)
        self.config = configparser.ConfigParser()
        self.config.read_file(old_conf)
        self.assertEqual(p.returncode, 1, 'The command must exit 1')

    def test_unsupported_driver(self):
        """Test that token generation is not possible with wrong driver"""
        old_conf = io.StringIO()
        self.config.write(old_conf)
        self.config.set('auth zuul_operator', 'driver', 'RS256withJWKS')
        self.config.write(
            open(os.path.join(self.test_root, 'JWKS.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'JWKS.conf'),
             'create-auth-token',
             '--user', 'marshmallow_man',
             '--action', 'autohold',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        old_conf.seek(0)
        self.config = configparser.ConfigParser()
        self.config.read_file(old_conf)
        self.assertEqual(p.returncode, 1, 'The command must exit 1')

    def test_unsupported_action(self):
        """Test that token generation is not possible with wrong action"""
        self.config.write(
            open(os.path.join(self.test_root, 'good.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'good.conf'),
             'create-auth-token',
             '--user', 'marshmallow_man',
             '--action', 'cross_the_streams',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 1, 'The command must exit 1')

    def test_token_generation(self):
        """Test token generation"""
        self.config.write(
            open(os.path.join(self.test_root, 'good.conf'), 'w'))
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'good.conf'),
             'create-auth-token',
             '--user', 'marshmallow_man',
             '--action', 'dequeue',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        now = time.time()
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        self.assertTrue(out.startswith(b"Bearer "), out)
        # there is a trailing carriage return in the output
        token = jwt.decode(out[len("Bearer "):-1],
                           key=self.config.get(
                               'auth zuul_operator',
                               'key'),
                           algorithm=self.config.get(
                               'auth zuul_operator',
                               'driver'))
        self.assertEqual('marshmallow_man', token.get('sub'))
        self.assertEqual('zuul_operator', token.get('iss'))
        self.assertEqual('zuul.example.com', token.get('aud'))
        actions = token.get('zuul.actions', {})
        self.assertTrue('dequeue' in actions, actions)
        self.assertTrue('tenant_one' in actions['dequeue'], actions)
        for p in ['projectA', 'projectB']:
            self.assertTrue(p in actions['dequeue']['tenant_one'])
        # allow one minute for the process to run
        self.assertTrue(600 <= int(token['exp']) - now < 660,
                        (token['exp'], now))
        # do not scope to projects, default expiry
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             '-c', os.path.join(self.test_root, 'activated.conf'),
             'create-auth-token',
             '--user', 'gozer'
             '--action', 'autohold',
             '--tenant', 'tenant_one'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        token = jwt.decode(out[len("Bearer "):-1],
                           key=self.config.get(
                               'auth zuul_operator',
                               'key'),
                           algorithm=self.config.get(
                               'auth zuul_operator',
                               'driver'))
        self.assertEqual('gozer', token.get('sub'))
        self.assertEqual('zuul_operator', token.get('iss'))
        self.assertEqual('zuul.example.com', token.get('aud'))
        actions = token.get('zuul.actions', {})
        self.assertTrue('autohold' in actions, actions)
        self.assertTrue('tenant_one' in actions['autohold'], actions)
        self.assertEqual('*', actions['autohold']['tenant_one'], actions)
