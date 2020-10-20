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

from zuul.lib import encryption
from zuul.lib import keystorage
from zuul.zk import ZooKeeperClient

from tests.base import BaseTestCase


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

        self.setupZK()
        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca)
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()

    def test_backup(self):
        root = self.useFixture(fixtures.TempDir()).path
        backup = keystorage.FileKeyStorage(root)
        key_store = keystorage.ZooKeeperKeyStorage(
            self.zk_client, password="DEADBEEF", backup=backup)

        # Create keys in the backup keystore
        backup_secrets_pk = encryption.serialize_rsa_private_key(
            backup.getProjectSecretsKeys("github", "org/project")[0])
        backup_ssh_keys = backup.getProjectSSHKeys("github", "org/project")

        self.assertEqual(
            encryption.serialize_rsa_private_key(
                key_store.getProjectSecretsKeys("github", "org/project")[0]
            ), backup_secrets_pk)
        self.assertEqual(
            key_store.getProjectSSHKeys("github", "org/project"),
            backup_ssh_keys)

        # Keys should initially not be in the backup keystore
        self.assertFalse(
            backup.hasProjectSecretsKeys("github", "org/project1"))
        self.assertFalse(
            backup.hasProjectSSHKeys("github", "org/project1"))

        self.assertIsNotNone(
            key_store.getProjectSecretsKeys("github", "org/project1"))
        self.assertIsNotNone(
            key_store.getProjectSSHKeys("github", "org/project1"))

        # Keys should now also exist in the backup keystore
        self.assertTrue(
            backup.hasProjectSecretsKeys("github", "org/project1"))
        self.assertTrue(
            backup.hasProjectSSHKeys("github", "org/project1"))

    def test_without_backup(self):
        key_store = keystorage.ZooKeeperKeyStorage(
            self.zk_client, password="DECAFBAD")
        secrets_pk = encryption.serialize_rsa_private_key(
            key_store.getProjectSecretsKeys("github", "org/project")[0])
        ssh_keys = key_store.getProjectSSHKeys("github", "org/project")

        self.assertEqual(
            encryption.serialize_rsa_private_key(
                key_store.getProjectSecretsKeys("github", "org/project")[0]
            ), secrets_pk)
        self.assertEqual(key_store.getProjectSSHKeys("github", "org/project"),
                         ssh_keys)
