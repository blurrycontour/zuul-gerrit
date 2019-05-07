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

        subparsers = parser.add_subparsers(title='commands',
                                           description='valid commands')

        cmd_prep_workspace = subparsers.add_parser(
            'prepare-workspace',
            help='checks out all of the required playbooks and roles into '
                 'a given workspace and returns the order of execution')
        cmd_prep_workspace.add_argument(
            '-d', '--job-dir', default=None,
            help='the directory to prepare inside of. Defaults to a temp dir')
        cmd_prep_workspace.set_defaults(func=self.prep_workspace)

        cmd_execute = subparsers.add_parser(
            'execute', help='prepare and execute a zuul jobs')
        cmd_execute.add_argument(
            '-n', '--nodes', action='append',
            help='A node to use, semi-colon separated tuple '
                 'of connection:label:hostname:username:cwd')
        cmd_execute.add_argument(
            '--skip-ansible-install', action='store_true',
            help='Skip ansible install and validation')
        cmd_execute.add_argument(
            '-d', '--job-dir', default=None,
            help='the directory to prepare inside of. defaults to a temp dir')
        cmd_execute.set_defaults(func=self.execute)

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
        if getattr(self.args, "nodes", None) is not None:
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

    def _constructConnections(self, config):
        connections = zuul.lib.connections.ConnectionRegistry()
        url = os.path.join(config.api, "connections")
        for config in requests.get(url).json():
            config['user'] = os.environ.get("USER", "zuul")
            connections.connections[config['name']] = connections.drivers[
                config['driver']].getConnection(config['name'], config)
        return connections

    def prep_workspace(self):
        self.runner.prepareWorkspace()
        job = self.runner.ansible_job
        print("== Pre phase ==")
        for index, playbook in enumerate(job.jobdir.pre_playbooks):
            print(playbook.path)
        print("== Run phase ==")
        for index, playbook in enumerate(job.jobdir.playbooks):
            print(playbook.path)
        print("== Post phase ==")
        for index, playbook in enumerate(job.jobdir.post_playbooks):
            print(playbook.path)

    def execute(self):
        print(self.runner.execute(self.args.skip_ansible_install))

    def main(self):
        self.parseArguments()
        # TODO: use zuul common logging
        # self.setup_logging()
        # in the meantime, enable debug
        logging.basicConfig(
            format='%(asctime)s %(levelname)-5.5s %(name)s - %(message)s',
            level=logging.DEBUG if self.args.verbose else logging.WARNING)

        config = zuul.executor.runner.RunnerConfiguration()
        runner_config = {}
        try:
            config.loadConfig(runner_config, self.args)
        except voluptuous.error.Invalid as e:
            print("Configuration error:", str(e))
            sys.exit(1)

        # Help user setting the correct API url
        if not config.api.endswith('/'):
            config.api += '/'
        if "/api/" not in config.api:
            config.api = os.path.join(config.api, "api")

        connections = self._constructConnections(config)

        self.runner = zuul.executor.runner.LocalRunnerContextManager(
            config, connections)

        try:
            if self.args.func():
                return 0
        except Exception as e:
            if self.args.verbose:
                raise
            print("Error: %s" % str(e))
        return 1


def main():
    sys.exit(Runner().main())


if __name__ == "__main__":
    main()
