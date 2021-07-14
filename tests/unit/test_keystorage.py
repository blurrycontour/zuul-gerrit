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

from zuul.lib import encryption
from zuul.lib import keystorage
from zuul.zk import ZooKeeperClient

from tests.base import BaseTestCase


class TestKeyStorage(BaseTestCase):

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

    def test_keystore(self):
        key_store = keystorage.KeyStorage(
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
