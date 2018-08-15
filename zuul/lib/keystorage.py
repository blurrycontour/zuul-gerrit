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

import logging
import os


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
            if int(f) == version:
                return True
        raise Exception("Unknown key storage version")

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
            parent = self.parent()
            parent.verifyAndUpgrade(root)
        self.log.info("Upgrading key storage to version %s" % self.version)
        self.upgrade(root)
        self.writeVersion(root)
        self.log.info("Finished upgrading key storage to version %s" % self.version)


class MigrationV2(Migration):
    version = 2
    parent = None

    """Upgrade from the unversioned schema to version 2.

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
    case, they will all be 1.

    """

    def upgrade(self, root):
        tmpdir = os.path.join(root, '.zuul_migration')
        os.mkdir(tmpdir)
        connection_names = []
        for connection_name in os.listdir(root):
            if connection_name == '.zuul_migration':
                continue
            # Move existing connections out of the way (in case one of
            # them was called 'secrets' or 'ssh' -- marginally more
            # likely than '.zuul_migration').
            os.rename(os.path.join(root, connection_name),
                      os.path.join(tmpdir, connection_name))
            connection_names.append(connection_name)
        os.mkdir(os.path.join(root, 'secrets'))
        os.mkdir(os.path.join(root, 'secrets', 'project'))
        os.mkdir(os.path.join(root, 'ssh'))
        os.mkdir(os.path.join(root, 'ssh', 'project'))
        os.mkdir(os.path.join(root, 'ssh', 'tenant'))
        for connection_name in connection_names:
            for key_name in os.listdir(os.path.join(tmpdir, connection_name)):
                project_name = key_name[:-len('.pem')]
                key_dir = os.path.join(root, 'secrets', 'project', connection_name, project_name)
                os.makedirs(key_dir)
                os.rename(os.path.join(tmpdir, connection_name, key_name),
                          os.path.join(key_dir, '1.pem'))
            os.rmdir(os.path.join(tmpdir, connection_name))
        os.rmdir(tmpdir)


class KeyStorage(object):
    current_version = MigrationV2

    def __init__(self, root):
        self.root = root
        migration = self.current_version()
        migration.verifyAndUpgrade(root)
