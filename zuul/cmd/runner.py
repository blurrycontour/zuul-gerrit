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
import sys

import zuul.cmd


class Runner(zuul.cmd.ZuulApp):
    app_name = 'runner'
    app_description = 'A helper script for running zuul jobs locally.'
    log = logging.getLogger("zuul.Runner")

    def createParser(self):
        parser = super(Runner, self).createParser()
        parser.add_argument('-v', dest='verbose', action='store_true',
                            help='verbose output')
        parser.add_argument('-r', '--runner-config',
                            default='~/.config/zuul/runner.yaml',
                            help='zuul-runner.yaml configuration file path')
        parser.add_argument('-a', '--api', required=True,
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
        parser.add_argument('-g', '--git-dir', default='~/.cache/zuul/git',
                            help='the git merger dir')

        subparsers = parser.add_subparsers(title='commands',
                                           description='valid commands')

        cmd_prep_workspace = subparsers.add_parser(
            'prep-workspace',
            help='checks out all of the required playbooks and roles into '
                 'a given workspace and returns the order of execution')
        cmd_prep_workspace.set_defaults(func=self.prep_workspace)
        cmd_prep_workspace.add_argument(
            '--dir', '--directory', default=None,
            help='the directory to prepare inside of. Defaults to a temp dir')

        # TODO(jhesketh):
        #  - Enable command line argument override from environ
        #  - Allow supplying the job via either raw input or zuul endpoint
        #  - Overwrite, warn, or exit on conflicting workspace entries
        #  - Add zuul-runner.yaml configuration

        return parser

    def parseArguments(self, args=None):
        parser = super(Runner, self).parseArguments()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)

    def _constructConnections(self):
        # Rebuild the connections necessary for the job (specifically
        # getSource). This may involve querying the zuul server for public
        # attributes such as baseurl.
        # TODO
        connections = zuul.lib.connections.ConnectionRegistry()

        # In the meantime, just load zuul.conf
        if self.args.config:
            self.readConfig()
        connections.configure(self.config, source_only=True)
        return connections

    def prep_workspace(self):
        job = self.runner.prepare_workspace()
        print("== Pre phase ==")
        for index, playbook in enumerate(job.jobdir.pre_playbooks):
            print(playbook.path)
        print("== Run phase ==")
        print(job.jobdir.playbook.path)
        print("== Post phase ==")
        for index, playbook in enumerate(job.jobdir.post_playbooks):
            print(playbook.path)

    def main(self):
        self.parseArguments()
        config = zuul.executor.runner.RunnerConfiguration()
        runner_config = config.readConfig(self.args.runner_config)
        config.loadConfig(runner_config, self.args)
        # TODO: use common logging
        # self.setup_logging()
        # in the meantime, enable debug
        logging.basicConfig(
            format='%(asctime)s %(levelname)-5.5s %(name)s - %(message)s',
            level=logging.DEBUG)

        connections = self._constructConnections()
        self.runner = zuul.executor.runner.Runner(config, connections)

        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)


def main():
    Runner().main()


if __name__ == "__main__":
    main()
