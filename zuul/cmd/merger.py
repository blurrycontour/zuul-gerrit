#!/usr/bin/env python
# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013-2014 OpenStack Foundation
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

import signal
import sys
from zuul.lib.config import get_default
import zuul.cmd
import zuul.merger.server
import zuul.zk


class Merger(zuul.cmd.ZuulDaemonApp):
    app_name = 'merger'
    app_description = 'A standalone Zuul merger.'

    def createParser(self):
        parser = super(Merger, self).createParser()
        parser.add_argument('command',
                            choices=zuul.merger.server.COMMANDS,
                            nargs='?')
        return parser

    def parseArguments(self, args=None):
        super(Merger, self).parseArguments()
        if self.args.command:
            self.args.nodaemon = True

    def exit_handler(self, signum, frame):
        self.merger.stop()
        self.merger.join()
        sys.exit(0)

    def run(self):
        if self.args.command in zuul.merger.server.COMMANDS:
            self.send_command(self.args.command)
            sys.exit(0)

        self.configure_connections(source_only=True)

        self.setup_logging('merger', 'log_config')

        zookeeper = zuul.zk.ZooKeeper(enable_cache=True)
        zookeeper_hosts = get_default(self.config, 'zookeeper', 'hosts', None)
        if not zookeeper_hosts:
            raise Exception("The zookeeper hosts config value is required")
        zookeeper_timeout = float(get_default(self.config, 'zookeeper',
                                              'session_timeout', 10.0))

        zookeeper.connect(zookeeper_hosts, timeout=zookeeper_timeout)

        self.merger = zuul.merger.server.MergeServer(self.config,
                                                     self.connections)
        self.merger.setZookeeper(zookeeper)
        self.merger.start()

        if self.args.nodaemon:
            signal.signal(signal.SIGTERM, self.exit_handler)
            while True:
                try:
                    signal.pause()
                except KeyboardInterrupt:
                    print("Ctrl + C: asking merger to exit nicely...\n")
                    self.exit_handler(signal.SIGINT, None)
        else:
            self.merger.join()


def main():
    Merger().main()


if __name__ == "__main__":
    main()
