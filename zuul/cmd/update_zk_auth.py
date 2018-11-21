# Copyright 2020 Red Hat
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

import zuul.cmd
import zuul.zk
import zuul.zk_auth
from zuul.lib.config import get_default


class UpdateZKAuth(zuul.cmd.ZuulApp):
    app_name = 'update-zk-auth'
    app_description = 'A zookeeper auth updater process.'

    def createParser(self):
        parser = super().createParser()
        parser.add_argument(
            "--chroot", help="zookeeper root nodes", action='append')
        return parser

    def main(self):
        self.parseArguments()
        self.readConfig()

        zookeeper_hosts = get_default(self.config, 'zookeeper', 'hosts', None)
        if not zookeeper_hosts:
            raise Exception("The zookeeper hosts config value is required")

        zk_auth = zuul.zk_auth.from_config(self.config)
        zk_acl = zk_auth.getACL()

        if not self.args.chroot:
            self.args.chroot = ["/zuul", "/nodepool"]

        zk = zuul.zk.ZooKeeper()
        zk.connect(zookeeper_hosts, auth_data=zk_auth)

        # Check we can access root node
        if any([not zk.client.exists(chroot) for chroot in self.args.chroot]):
            print("error: can't access %s node" % " ".join(self.args.chroot))
            exit(1)

        # Ask for confirmation
        try:
            if input("Update zookeeper %s ACL? [Y/n] " %
                     " ".join(self.args.chroot)).strip() not in ('y', 'Y', ''):
                exit(1)
        except KeyboardInterrupt:
            exit(1)

        def walk(node):
            for child in zk.client.get_children(node):
                for child_node in walk(os.path.join(node, child)):
                    yield child_node
            yield node

        for chroot in self.args.chroot:
            for node in walk(chroot):
                zk.client.set_acls(node, zk_acl)
        print("Done.")


def main():
    UpdateZKAuth().main()


if __name__ == "__main__":
    main()
