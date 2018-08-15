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
import fixtures

from zuul.lib import keystorage

from tests.base import BaseTestCase


class TestKeyStorage(BaseTestCase):

    def _setup_keys(self, root, connection_name, project_name):
        dn = os.path.join(root, connection_name)
        os.makedirs(dn)
        fn = os.path.join(dn, project_name + '.pem')
        with open(fn, 'w') as f:
            pass

    def assertFile(self, root, path, contents=None):
        fn = os.path.join(root, path)
        self.assertTrue(os.path.exists(fn))
        if contents:
            with open(fn) as f:
                self.assertEqual(contents, f.read())

    def assertPaths(self, root, paths):
        seen = set()
        for dirpath, dirnames, filenames in os.walk(root):
            for d in dirnames:
                seen.add(os.path.join(dirpath[len(root)+1:], d))
            for f in filenames:
                seen.add(os.path.join(dirpath[len(root)+1:], f))
        self.assertEqual(set(paths), seen)

    def test_key_storage(self):
        root = self.useFixture(fixtures.TempDir()).path
        self._setup_keys(root, 'gerrit', 'example')
        ks = keystorage.KeyStorage(root)
        self.assertFile(root, '.version', '2')
        self.assertPaths(root, [
            '.version',
            'secrets',
            'secrets/project',
            'secrets/project/gerrit',
            'secrets/project/gerrit/example',
            'secrets/project/gerrit/example/1.pem',
            'ssh',
            'ssh/project',
            'ssh/tenant',
        ])
