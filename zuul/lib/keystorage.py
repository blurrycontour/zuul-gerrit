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

import abc
import io
import json
import logging
import os
import tempfile
import time

import cachetools
import kazoo
import paramiko

from zuul.lib import encryption, strings
from zuul.zk import ZooKeeperBase

RSA_KEY_SIZE = 2048


class Migration(object):
    log = logging.getLogger("zuul.KeyStorage")
    version = 0
    parent = None

    def verify(self, root):
        fn = os.path.join(root, '.version')
        if not os.path.exists(fn):
            return False
        with open(fn) as f:
            data = int(f.read().strip())
            if data == self.version:
                return True
        return False

    def writeVersion(self, root):
        fn = os.path.join(root, '.version')
        with open(fn, 'w') as f:
            f.write(str(self.version))

    def upgrade(self, root):
        pass

    def verifyAndUpgrade(self, root):
        if self.verify(root):
            return
        if self.parent:
            self.parent.verifyAndUpgrade(root)
        self.log.info("Upgrading key storage to version %s" % self.version)
        self.upgrade(root)
        self.writeVersion(root)
        self.log.info("Finished upgrading key storage to version %s" %
                      self.version)
        if not self.verify(root):
            raise Exception("Inconsistent result after migration")


class MigrationV1(Migration):
    version = 1
    parent = None

    """Upgrade from the unversioned schema to version 1.

    The original schema had secret keys in key_dir/connection/project.pem

    This updates us to:
      key_dir/
        secrets/
          project/
            <connection>/
              <project>/
                <keyid>.pem
        ssh/
          project/
            <connection>/
              <project>/
                <keyid>.pem
          tenant/
            <tenant>/
              <keyid>.pem

    Where keyids are integers to support future key rollover.  In this
    case, they will all be 0.

    """

    def upgrade(self, root):
        tmpdir = tempfile.mkdtemp(dir=root)
        tmpdirname = os.path.basename(tmpdir)
        connection_names = []
        for connection_name in os.listdir(root):
            if connection_name == tmpdirname:
                continue
            # Move existing connections out of the way (in case one of
            # them was called 'secrets' or 'ssh'.
            os.rename(os.path.join(root, connection_name),
                      os.path.join(tmpdir, connection_name))
            connection_names.append(connection_name)
        os.makedirs(os.path.join(root, 'secrets', 'project'), 0o700)
        os.makedirs(os.path.join(root, 'ssh', 'project'), 0o700)
        os.makedirs(os.path.join(root, 'ssh', 'tenant'), 0o700)
        for connection_name in connection_names:
            connection_root = os.path.join(tmpdir, connection_name)
            for (dirpath, dirnames, filenames) in os.walk(connection_root):
                subdir = os.path.relpath(dirpath, connection_root)
                for fn in filenames:
                    key_name = os.path.join(subdir, fn)
                    project_name = key_name[:-len('.pem')]
                    key_dir = os.path.join(root, 'secrets', 'project',
                                           connection_name, project_name)
                    os.makedirs(key_dir, 0o700)
                    old = os.path.join(tmpdir, connection_name, key_name)
                    new = os.path.join(key_dir, '0.pem')
                    self.log.debug("Moving key from %s to %s", old, new)
                    os.rename(old, new)
            for (dirpath, dirnames, filenames) in os.walk(
                    connection_root, topdown=False):
                os.rmdir(dirpath)
        os.rmdir(tmpdir)


class KeyStorage(abc.ABC):
    log = logging.getLogger("zuul.KeyStorage")

    @abc.abstractmethod
    def getProjectSSHKeys(self, connection_name, project_name):
        """Return the private and public SSH keys for the project

        A new key will be created if necessary.

        :returns: A tuple containing the PEM encoded private key and
                  base64 encoded public key.
        """
        pass

    @abc.abstractmethod
    def getProjectSecretsKeys(self, connection_name, project_name):
        """Return the private and public secrets keys for the project

        A new key will be created if necessary.

        :returns: A tuple (private_key, public_key)
        """
        pass


class FileKeyStorage(KeyStorage):
    log = logging.getLogger("zuul.FileKeyStorage")
    current_version = MigrationV1

    def __init__(self, root):
        self.root = root
        migration = self.current_version()
        migration.verifyAndUpgrade(root)

    def getProjectSecretsKeyFile(self, connection, project, version=None):
        """Return the path to the private key used for the project's secrets"""
        # We don't actually support multiple versions yet
        if version is None:
            version = '0'
        return os.path.join(self.root, 'secrets', 'project',
                            connection, project, version + '.pem')

    def getProjectSSHKeyFile(self, connection, project, version=None):
        """Return the path to the private ssh key for the project"""
        # We don't actually support multiple versions yet
        if version is None:
            version = '0'
        return os.path.join(self.root, 'ssh', 'project',
                            connection, project, version + '.pem')

    def hasProjectSSHKeys(self, connection_name, project_name):
        return os.path.isfile(
            self.getProjectSSHKeyFile(connection_name, project_name))

    def setProjectSSHKey(self, connection_name, project_name, private_key):
        private_key_file = self.getProjectSSHKeyFile(connection_name,
                                                     project_name)
        key_dir = os.path.dirname(private_key_file)
        if not os.path.isdir(key_dir):
            os.makedirs(key_dir, 0o700)

        private_key.write_private_key_file(private_key_file)
        return private_key_file

    def getProjectSSHKeys(self, connection_name, project_name):
        private_key_file = self._ensureSSHKeyFile(connection_name,
                                                  project_name)

        key = paramiko.RSAKey.from_private_key_file(private_key_file)
        with open(private_key_file, 'r') as f:
            private_key = f.read()
        public_key = key.get_base64()

        return (private_key, 'ssh-rsa ' + public_key)

    def _ensureSSHKeyFile(self, connection_name, project_name):
        private_key_file = self.getProjectSSHKeyFile(connection_name,
                                                     project_name)
        if os.path.exists(private_key_file):
            return private_key_file

        self.log.info("Generating SSH public key for project %s", project_name)
        pk = paramiko.RSAKey.generate(bits=RSA_KEY_SIZE)
        return self.setProjectSSHKey(connection_name, project_name, pk)

    def hasProjectSecretsKeys(self, connection_name, project_name):
        return os.path.isfile(
            self.getProjectSecretsKeyFile(connection_name, project_name))

    def setProjectSecretsKey(self, connection_name, project_name, private_key):
        filename = self.getProjectSecretsKeyFile(connection_name, project_name)
        key_dir = os.path.dirname(filename)
        if not os.path.isdir(key_dir):
            os.makedirs(key_dir, 0o700)

        # Dump keys to filesystem.  We only save the private key
        # because the public key can be constructed from it.
        self.log.info("Saving RSA keypair for project %s to %s",
                      project_name, filename)

        pem_private_key = encryption.serialize_rsa_private_key(private_key)
        # Ensure private key is read/write for zuul user only.
        with open(os.open(filename,
                          os.O_CREAT | os.O_WRONLY, 0o600), 'wb') as f:
            f.write(pem_private_key)
        return filename

    def getProjectSecretsKeys(self, connection_name, project_name):
        private_key_file = self._ensureSecretsKeyFile(connection_name,
                                                      project_name)

        # Load keypair
        with open(private_key_file, "rb") as f:
            return encryption.deserialize_rsa_keypair(f.read())

    def _ensureSecretsKeyFile(self, connection_name, project_name):
        filename = self.getProjectSecretsKeyFile(connection_name, project_name)
        if os.path.isfile(filename):
            return filename

        self.log.info("Generating RSA keypair for project %s", project_name)
        private_key, public_key = encryption.generate_rsa_keypair()

        return self.setProjectSecretsKey(connection_name, project_name,
                                         private_key)


class ZooKeeperKeyStorage(ZooKeeperBase, KeyStorage):
    log = logging.getLogger("zuul.ZooKeeperKeyStorage")
    SECRETS_PATH = "/keystorage/{}/{}/secrets"
    SSH_PATH = "/keystorage/{}/{}/ssh"

    def __init__(self, zookeeper_client, password, backup=None):
        super().__init__(zookeeper_client)
        self.password = password
        self.password_bytes = password.encode("utf-8")
        self.backup = backup

    @cachetools.cached(cache={})
    def getProjectSSHKeys(self, connection_name, project_name):
        key_project_name = strings.unique_project_name(project_name)
        key_path = self.SSH_PATH.format(connection_name, key_project_name)

        try:
            key = self._getSSHKey(key_path)
        except kazoo.exceptions.NoNodeError:
            self.log.debug("Could not find existing SSH key for %s/%s",
                           connection_name, project_name)
            if self.backup and self.backup.hasProjectSSHKeys(
                connection_name, project_name
            ):
                self.log.info("Using SSH key for %s/%s from backup key store",
                              connection_name, project_name)
                pk, _ = self.backup.getProjectSSHKeys(connection_name,
                                                      project_name)
                with io.StringIO(pk) as o:
                    key = paramiko.RSAKey.from_private_key(o)
            else:
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

        # Make sure the SSH key is also stored in the backup keystore
        if self.backup:
            self.backup.setProjectSSHKey(connection_name, project_name, key)

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

    @cachetools.cached(cache={})
    def getProjectSecretsKeys(self, connection_name, project_name):
        key_project_name = strings.unique_project_name(project_name)
        key_path = self.SECRETS_PATH.format(connection_name, key_project_name)

        try:
            pem_private_key = self._getSecretsKeys(key_path)
        except kazoo.exceptions.NoNodeError:
            self.log.debug("Could not find existing secrets key for %s/%s",
                           connection_name, project_name)
            if self.backup and self.backup.hasProjectSecretsKeys(
                    connection_name, project_name):
                self.log.info(
                    "Using secrets key for %s/%s from backup key store",
                    connection_name, project_name)
                private_key, public_key = self.backup.getProjectSecretsKeys(
                    connection_name, project_name)
            else:
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

        # Make sure the private key is also stored in the backup keystore
        if self.backup:
            self.backup.setProjectSecretsKey(connection_name, project_name,
                                             private_key)

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
