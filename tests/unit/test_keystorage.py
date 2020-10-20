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

import zuul.zk
from zuul.lib import encryption
from zuul.lib import keystorage

from tests.base import BaseTestCase, ChrootedKazooFixture


class TestFileKeyStorage(BaseTestCase):

    def _setup_keys(self, root, connection_name, project_name):
        cn = os.path.join(root, connection_name)
        if '/' in project_name:
            pn = os.path.join(cn, os.path.dirname(project_name))
        os.makedirs(pn)
        fn = os.path.join(cn, project_name + '.pem')
        with open(fn, 'w'):
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
                seen.add(os.path.join(dirpath[len(root) + 1:], d))
            for f in filenames:
                seen.add(os.path.join(dirpath[len(root) + 1:], f))
        self.assertEqual(set(paths), seen)

    def test_key_storage(self):
        root = self.useFixture(fixtures.TempDir()).path
        self._setup_keys(root, 'gerrit', 'org/example')
        keystorage.FileKeyStorage(root)
        self.assertFile(root, '.version', '1')
        self.assertPaths(root, [
            '.version',
            'secrets',
            'secrets/project',
            'secrets/project/gerrit',
            'secrets/project/gerrit/org',
            'secrets/project/gerrit/org/example',
            'secrets/project/gerrit/org/example/0.pem',
            'ssh',
            'ssh/project',
            'ssh/tenant',
        ])
        # It shouldn't need to upgrade this time
        keystorage.FileKeyStorage(root)


class TestZooKeeperKeyStorage(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.zk_chroot_fixture = self.useFixture(
            ChrootedKazooFixture(self.id()))
        self.zk_config = '%s:%s%s' % (
            self.zk_chroot_fixture.zookeeper_host,
            self.zk_chroot_fixture.zookeeper_port,
            self.zk_chroot_fixture.zookeeper_chroot)

        self.zk = zuul.zk.ZooKeeper()
        self.addCleanup(self.zk.disconnect)
        self.zk.connect(self.zk_config)

    def test_fallback(self):
        root = self.useFixture(fixtures.TempDir()).path
        fallback = keystorage.FileKeyStorage(root)
        key_store = keystorage.ZooKeeperKeyStorage(
            self.zk.client, password="DEADBEEF", fallback=fallback
        )

        # Create keys in the fallback keystore
        fallback_secrets_pk = encryption.serialize_rsa_private_key(
            fallback.getProjectSecretsKeys("github", "org/project")[0]
        )
        fallback_ssh_keys = fallback.getProjectSSHKeys("github", "org/project")

        self.assertEqual(
            encryption.serialize_rsa_private_key(
                key_store.getProjectSecretsKeys("github", "org/project")[0]
            ),
            fallback_secrets_pk
        )
        self.assertEqual(
            key_store.getProjectSSHKeys("github", "org/project"),
            fallback_ssh_keys
        )

        self.assertIsNotNone(
            key_store.getProjectSecretsKeys("github", "org/project1")
        )
        self.assertIsNotNone(
            key_store.getProjectSSHKeys("github", "org/project1")
        )

        # New keys should not end up in the fallback key store
        self.assertFalse(
            fallback.hasProjectSecretsKeys("github", "org/project1")
        )
        self.assertFalse(fallback.hasProjectSSHKeys("github", "org/project1"))

    def test_without_fallback(self):
        key_store = keystorage.ZooKeeperKeyStorage(
            self.zk.client, password="DECAFBAD"
        )
        secrets_pk = encryption.serialize_rsa_private_key(
            key_store.getProjectSecretsKeys("github", "org/project")[0]
        )
        ssh_keys = key_store.getProjectSSHKeys("github", "org/project")

        self.assertEqual(
            encryption.serialize_rsa_private_key(
                key_store.getProjectSecretsKeys("github", "org/project")[0]
            ),
            secrets_pk
        )
        self.assertEqual(
            key_store.getProjectSSHKeys("github", "org/project"),
            ssh_keys
        )
