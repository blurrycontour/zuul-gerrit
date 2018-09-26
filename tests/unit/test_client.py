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

import os
import sys
import subprocess
import time

import configparser
import fixtures
import jwt

from tests.base import BaseTestCase
from tests.base import FIXTURE_DIR


class TestTenantValidationClient(BaseTestCase):
    config_file = 'zuul.conf'

    def setUp(self):
        super(TestTenantValidationClient, self).setUp()
        self.test_root = self.useFixture(fixtures.TempDir(
            rootdir=os.environ.get("ZUUL_TEST_ROOT"))).path
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(FIXTURE_DIR, self.config_file))

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


class TestWebTokenClient(TestTenantValidationClient):

    def test_create_web_token(self):
        # admin endpoints are not up
        self.config.set(
            'web', 'enable_admin_endpoints', False)
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             'create-web-token',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 1, 'The command must exit 1')
        # Test multiple projects
        self.config.set(
            'web', 'enable_admin_endpoints', True)
        self.config.set(
            'web', 'JWTsecret', 'StayPuft')
        self.config.set(
            'web', 'JWTalgorithm', 'HS256')
        self.config.set(
            'web', 'JWTexpiry', '3600')
        now = time.time()
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             'create-web-token',
             '--user', 'marshmallow_man',
             '--tenant', 'tenant_one',
             '--project', 'projectA', 'projectB'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        self.assertIn("Bearer ", out, out)
        token = jwt.decode(out[len("Bearer "):],
                           key='StayPuft',
                           algorithm='HS256')
        self.assertEqual('marshmallow_man', token.get('sub'))
        self.assertEqual('Zuul CLI', token.get('iss'))
        tenants = token.get('zuul.tenants', {})
        self.assertTrue('tenant_one' in tenants, tenants)
        for p in ['projectA', 'projectB']:
            self.assertTrue(p in tenants['tenant_one'], tenants)
        # allow one minute for the process to run
        self.assertTrue(3600 <= int(token['exp']) - now < 3660,
                        token['exp'])
        # do not scope to projects, no user either
        p = subprocess.Popen(
            [os.path.join(sys.prefix, 'bin/zuul'),
             'create-web-token',
             '--tenant', 'tenant_one'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()
        self.assertEqual(p.returncode, 0, 'The command must exit 0')
        self.assertIn("Bearer ", out, out)
        token = jwt.decode(out[len("Bearer "):],
                           key='StayPuft',
                           algorithm='HS256')
        self.assertEqual(None, token.get('sub'))
        tenants = token.get('zuul.tenants', {})
        self.assertTrue('tenant_one' in tenants, tenants)
        self.assertEqual("*", tenants['tenant_one'], tenants)
