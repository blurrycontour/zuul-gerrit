#!/usr/bin/env python
# Copyright 2018 SUSE Linux GmbH
# Copyright 2019 Red Hat
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
import sys

import requests
import voluptuous.error

import zuul.cmd
import zuul.executor.runner


class Runner(zuul.cmd.ZuulApp):
    app_name = 'runner'
    app_description = 'A helper script for running zuul jobs locally.'
    log = logging.getLogger("zuul.Runner")

    def createParser(self):
        parser = super(Runner, self).createParser()
        parser.add_argument('-v', '--verbose', action='store_true',
                            help='verbose output')
        parser.add_argument('-r', '--runner-config',
                            default='~/.config/zuul/runner.yaml',
                            help='zuul-runner.yaml configuration file path')
        parser.add_argument('-k', '--key', default='~/.ssh/id_rsa',
                            help='the key to use for ssh connections')
        parser.add_argument('-a', '--api',
                            help='the zuul server api to query against')
        parser.add_argument('-t', '--tenant',
                            help='the zuul tenant name')
        parser.add_argument('-j', '--job',
                            help='the zuul job name')
        parser.add_argument('-P', '--pipeline',
                            help='the zuul pipeline name')
        parser.add_argument('-p', '--project',
                            help='the zuul project name')
        parser.add_argument('-b', '--branch',
                            help='the zuul project\'s branch name')
        parser.add_argument('-g', '--git-dir',
                            help='the git merger dir')
        parser.add_argument('-n', '--nodes', action='append',
                            help='A node to use, semi-colon separated tuple '
                                 'of connection:label:username:hostname:cwd')
        parser.add_argument('-d', '--directory', default=None,
                            help='the directory to prepare inside of. '
                            'Defaults to a temp dir')

        # TODO(jhesketh):
        #  - Enable command line argument override from environ
        #  - Allow supplying the job via either raw input or zuul endpoint
        #  - Overwrite, warn, or exit on conflicting workspace entries

        return parser

    def parseArguments(self, args=None):
        parser = super(Runner, self).parseArguments()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)
        # Parse node command line argument
        nodes = []
        if self.args.nodes:
            for node in self.args.nodes:
                try:
                    conn, label, hostname, user, cwd = node.split(':')
                except Exception as e:
                    print("Couldn't decode %s: %s" % (node, str(e)))
                    sys.exit(1)
                nodes.append(dict(
                    connection=conn,
                    label=label,
                    username=user,
                    hostname=hostname,
                    cwd=cwd,
                ))
        self.args.nodes = nodes

    def _constructConnections(self):
        connections = zuul.lib.connections.ConnectionRegistry()
        url = os.path.join(self.args.api, "connections")
        for config in requests.get(url).json():
            config['user'] = os.environ.get("USER", "zuul")
            config['sshkey'] = os.path.expanduser(self.args.key)
            connections.connections[config['name']] = connections.drivers[
                config['driver']].getConnection(config['name'], config)
        return connections

    def prep_workspace(self):
        job = self.runner.prep_workspace()
        print("== Pre phase ==")
        for index, playbook in enumerate(job.jobdir.pre_playbooks):
            print(playbook.path)
        print("== Run phase ==")
        for index, playbook in enumerate(job.jobdir.playbooks):
            print(playbook.path)
        print("== Post phase ==")
        for index, playbook in enumerate(job.jobdir.post_playbooks):
            print(playbook.path)

    def execute_job(self):
        job = self.runner.prep_workspace()
        try:
            print(self.runner.execute(job))
        except Exception:
            self.log.exception("Execute failed:")
            return False

    def main(self):
        self.parseArguments()
        # TODO: use zuul common logging
        # self.setup_logging()
        # in the meantime, enable debug
        logging.basicConfig(
            format='%(asctime)s %(levelname)-5.5s %(name)s - %(message)s',
            level=logging.DEBUG if self.args.verbose else logging.WARNING)

        config = zuul.executor.runner.RunnerConfiguration()
        runner_config = config.readConfig(self.args.runner_config)
        try:
            config.loadConfig(runner_config, self.args)
        except voluptuous.error.Invalid as e:
            print("Configuration error:", str(e))
            sys.exit(1)

        connections = self._constructConnections()

        # Apply local runner connection config
        for connection in config.connections:
            for name, zuul_connection in connections.connections.items():
                if name == connection.get('name'):
                    for k, v in connection.items():
                        setattr(zuul_connection, k, v)

        self.runner = zuul.executor.runner.Runner(config, connections)

        try:
            if not self.execute_job():
                sys.exit(1)
        except Exception as e:
            if self.args.verbose:
                raise
            print("Error: %s" % str(e))
            sys.exit(1)


def main():
    Runner().main()


if __name__ == "__main__":
    main()
