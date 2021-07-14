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
import json
import logging
import time

import cachetools
import kazoo
import paramiko

from zuul.lib import encryption, strings
from zuul.zk import ZooKeeperBase

RSA_KEY_SIZE = 2048


class KeyStorage(ZooKeeperBase):
    log = logging.getLogger("zuul.KeyStorage")
    SECRETS_PATH = "/keystorage/{}/{}/secrets"
    SSH_PATH = "/keystorage/{}/{}/ssh"

    def __init__(self, zookeeper_client, password, backup=None):
        super().__init__(zookeeper_client)
        self.password = password
        self.password_bytes = password.encode("utf-8")

    def _walk(self, root):
        ret = []
        children = self.kazoo_client.get_children(root)
        if children:
            for child in children:
                path = '/'.join([root, child])
                ret.extend(self._walk(path))
        else:
            data, _ = self.kazoo_client.get(root)
            try:
                ret.append((root, json.loads(data)))
            except Exception:
                self.log.error(f"Unable to load keys at {root}")
                # Keep processing exports
        return ret

    def exportKeys(self):
        keys = {}
        for (path, data) in self._walk('/keystorage'):
            self.log.info(f"Exported: {path}")
            keys[path] = data
        return {'keys': keys}

    def importKeys(self, import_data, overwrite):
        for path, data in import_data['keys'].items():
            if not path.startswith('/keystorage'):
                self.log.error(f"Invalid path: {path}")
                return
            data = json.dumps(data).encode('utf8')
            try:
                self.kazoo_client.create(path, value=data, makepath=True)
                self.log.info(f"Created key at {path}")
            except kazoo.exceptions.NodeExistsError:
                if overwrite:
                    self.kazoo_client.set(path, value=data)
                    self.log.info(f"Updated key at {path}")
                else:
                    self.log.warning(f"Not overwriting existing key at {path}")

    def getSSHKeysPath(self, connection_name, project_name):
        key_project_name = strings.unique_project_name(project_name)
        key_path = self.SSH_PATH.format(connection_name, key_project_name)
        return key_path

    @cachetools.cached(cache={})
    def getProjectSSHKeys(self, connection_name, project_name):
        key_path = self.getSSHKeysPath(connection_name, project_name)

        try:
            key = self._getSSHKey(key_path)
        except kazoo.exceptions.NoNodeError:
            self.log.info("Generating a new SSH key for %s/%s",
                          connection_name, project_name)
            key = paramiko.RSAKey.generate(bits=RSA_KEY_SIZE)
            key_version = 0
            key_created = int(time.time())

            try:
                self._storeSSHKey(key_path, key, key_version, key_created)
            except kazoo.exceptions.NodeExistsError:
                # Handle race condition between multiple schedulers
                # creating the same SSH key.
                key = self._getSSHKey(key_path)

        with io.StringIO() as o:
            key.write_private_key(o)
            private_key = o.getvalue()
        public_key = "ssh-rsa {}".format(key.get_base64())

        return private_key, public_key

    def _getSSHKey(self, key_path):
        data, _ = self.kazoo_client.get(key_path)
        keydata = json.loads(data)
        encrypted_key = keydata['keys'][0]["private_key"]
        with io.StringIO(encrypted_key) as o:
            return paramiko.RSAKey.from_private_key(o, self.password)

    def _storeSSHKey(self, key_path, key, version, created):
        # key is an rsa key object
        with io.StringIO() as o:
            key.write_private_key(o, self.password)
            private_key = o.getvalue()
        keys = [{
            "version": version,
            "created": created,
            "private_key": private_key,
        }]
        keydata = {
            'schema': 1,
            'keys': keys
        }
        data = json.dumps(keydata).encode("utf-8")
        self.kazoo_client.create(key_path, value=data, makepath=True)

    def getProjectSecretsKeysPath(self, connection_name, project_name):
        key_project_name = strings.unique_project_name(project_name)
        key_path = self.SECRETS_PATH.format(connection_name, key_project_name)
        return key_path

    @cachetools.cached(cache={})
    def getProjectSecretsKeys(self, connection_name, project_name):
        key_path = self.getProjectSecretsKeysPath(
            connection_name, project_name)

        try:
            pem_private_key = self._getSecretsKeys(key_path)
        except kazoo.exceptions.NoNodeError:
            self.log.info("Generating a new secrets key for %s/%s",
                          connection_name, project_name)
            private_key, public_key = encryption.generate_rsa_keypair()
            pem_private_key = encryption.serialize_rsa_private_key(
                private_key, self.password_bytes)
            key_version = 0
            key_created = int(time.time())

            try:
                self._storeSecretsKeys(key_path, pem_private_key,
                                       key_version, key_created)
            except kazoo.exceptions.NodeExistsError:
                # Handle race condition between multiple schedulers
                # creating the same secrets key.
                pem_private_key = self._getSecretsKeys(key_path)

        private_key, public_key = encryption.deserialize_rsa_keypair(
            pem_private_key, self.password_bytes)

        return private_key, public_key

    def _getSecretsKeys(self, key_path):
        data, _ = self.kazoo_client.get(key_path)
        keydata = json.loads(data)
        return keydata['keys'][0]["private_key"].encode("utf-8")

    def _storeSecretsKeys(self, key_path, key, version, created):
        # key is a pem-encoded (base64) private key stored in bytes
        keys = [{
            "version": version,
            "created": created,
            "private_key": key.decode("utf-8"),
        }]
        keydata = {
            'schema': 1,
            'keys': keys
        }
        data = json.dumps(keydata).encode("utf-8")
        self.kazoo_client.create(key_path, value=data, makepath=True)
