#!/usr/bin/env python
# Copyright 2018 SUSE Linux GmbH
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
import tempfile
import threading
import uuid

import requests

import zuul.cmd
import zuul.merger.merger
import zuul.lib.connections

from zuul.executor.common import JobDir, AnsibleJobBase, DeduplicateQueue
from zuul.executor.common import UpdateTask, SshAgent


class Runner(zuul.cmd.ZuulApp):
    app_name = 'runner'
    app_description = 'A helper script for running zuul jobs locally.'
    log = logging.getLogger("zuul.Runner")

    def createParser(self):
        parser = super(Runner, self).createParser()
        parser.add_argument('-v', dest='verbose', action='store_true',
                            help='verbose output')
        parser.add_argument('-a', '--api', required=True,
                            help='the zuul server api to query against')
        parser.add_argument('-t', '--tenant',
                            help='the zuul tenant name')
        parser.add_argument('-j', '--job',
                            help='the zuul job name')
        parser.add_argument('-P', '--pipeline', default='master',
                            help='the zuul pipeline name')
        parser.add_argument('-p', '--project',
                            help='the zuul project name')
        parser.add_argument('-b', '--branch', default='master',
                            help='the zuul project\'s branch name')

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

        cmd_execute = subparsers.add_parser(
            'execute',
            help='Execute a job locally, prepare-workspace if needed')
        cmd_execute.set_defaults(func=self.execute_job)
        cmd_execute.add_argument(
            '--dir', '--directory', default=None,
            help='the directory to prepare inside of. Defaults to a temp dir')

        self.job_params = None
        self.hostname = 'localhost'
        self.default_username = 'zuul-runner'
        self.verbose = False
        self.executor_variables_file = None
        self.ansible_dir = None
        self.statsd = None
        self.library_dir = os.path.realpath(
            os.path.join(__file__, "..", "..", "ansible", "library"))
        self.filter_dir = os.path.realpath(
            os.path.join(__file__, "..", "..", "ansible", "filter"))
        self.callback_dir = os.path.realpath(
            os.path.join(__file__, "..", "..", "ansible", "callback"))

        # TODO(jhesketh):
        #  - Allow setting the zuul instance endpoint from params or env vars
        #  - Allow supplying the job via either raw input or zuul endpoint
        #  - Overwrite, warn, or exit on conflicting workspace entries
        #  - Allow supplying own connection details or querying zuul sched

        return parser

    def parseArguments(self, args=None):
        parser = super(Runner, self).parseArguments()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)

    def _grab_frozen_job(self):
        url = self.args.api
        if self.args.tenant:
            url = os.path.join(url, "tenant", self.args.tenant)
        if self.args.project:
            url = os.path.join(
                url,
                "frozen_job",
                self.args.project,
                self.args.pipeline,
                self.args.branch)
        if self.args.job:
            url = os.path.join(url, self.args.job)
        return requests.get(url).json()

    def _constructConnections(self):
        # Rebuild the connections necessary for the job (specifically
        # getSource). This may involve querying the zuul server for public
        # attributes such as baseurl.
        # TODO
        connections = zuul.lib.connections.ConnectionRegistry()
        # In the meantime, just load zuul.conf
        self.readConfig()
        connections.configure(self.config, source_only=True)
        return connections

    def _updateLoop(self):
        while True:
            try:
                self._innerUpdateLoop()
            except Exception:
                self.log.exception("Exception in update thread:")

    def _innerUpdateLoop(self):
        # Inside of a loop that keeps the main repositories up to date
        task = self.update_queue.get()
        if task is None:
            # We are asked to stop
            return
        with self.merger_lock:
            self.log.info("Updating repo %s/%s" % (
                task.connection_name, task.project_name))
            self.merger.updateRepo(task.connection_name, task.project_name)
            repo = self.merger.getRepo(task.connection_name, task.project_name)
            source = self.connections.getSource(task.connection_name)
            project = source.getProject(task.project_name)
            task.canonical_name = project.canonical_name
            task.branches = repo.getBranches()
            task.refs = [r.name for r in repo.getRefs()]
            self.log.debug("Finished updating repo %s/%s" %
                           (task.connection_name, task.project_name))
        task.setComplete()

    def update(self, connection_name, project_name):
        # Update a repository in the main merger
        task = UpdateTask(connection_name, project_name)
        task = self.update_queue.put(task)
        return task

    def join(self):
        self.update_thread.join()

    def start_update_thread(self):
        self.update_queue = DeduplicateQueue()
        self.update_thread = threading.Thread(target=self._updateLoop,
                                              name='update')
        self.update_thread.daemon = True
        self.update_thread.start()

    def prep_environment(self):
        self.job_params = self._grab_frozen_job()
        self.connections = self._constructConnections()
        if self.args.dir:
            root = self.args.dir
            os.makedirs(root, exist_ok=True)
            exist_ok = True
        else:
            root = tempfile.mkdtemp()
            exist_ok = False
        uid = str(uuid.uuid4().hex)
        # TODO(tristanC): enable uuid cli argument
        uid = "test"
        self.merge_root = os.path.join(root, uid, "work", "src")
        self.job = AnsibleJobBase(
            self, self.job_params)
        self.jobdir = JobDir(
            root, keep=True, build_uuid=uid, exist_ok=exist_ok)
        self.job.jobdir = self.jobdir
        print("Working dir: %s" % self.job.jobdir.root)

    def prep_workspace(self):
        if not self.job_params:
            self.prep_environment()
        self.merger_lock = threading.Lock()
        self.merger = self.job.getMerger(
            self.merge_root, logger=None, execution_context=True)
        self.start_update_thread()
        # TODO(jhesketh):
        #  - Give options to clean up working dir
        #  - figure out what to do with build_uuid's
        self.job.prepareRepositories(self.update, exists_ok=True)

    def execute_job(self):
        if not self.job_params:
            self.prep_environment()

        self.prep_workspace()
        self.execution_wrapper = self.connections.drivers["bubblewrap"]

        # TODO(tristanC):
        #  - first enable user provided inventory
        #  - later user could provide nodepool.configuration and let the runner
        #    manage resources lifecycle...
        nodesets = {
            "name": "test-nodeset",
            "nodes": [{
                'name': ['test-instance'],
                'interface_ip': '127.0.0.1',
                'connection_port': 22,
                'connection_type': 'ssh',
                'username': 'zuul-worker'
            }],
            "groups": [],
        }
        self.job_params.update(nodesets)
        self.job.preparePlaybooks(self.job_params)
        self.job.prepareAnsibleFiles(self.job_params)
        self.job.writeLoggingConfig()

        self.job.ssh_agent = SshAgent()
        try:
            self.job.ssh_agent.start()
            # TODO: enable custom key
            self.job.ssh_agent.add(os.path.expanduser("~/.ssh/id_rsa"))
            print(self.job.runPlaybooks(self.job_params))
        finally:
            self.job.ssh_agent.stop()

    def main(self):
        self.parseArguments()
        # TODO: use common logging
        # self.setup_logging()
        # in the meantime, enable debug
        logging.basicConfig(
            format='%(asctime)s %(levelname)-5.5s %(name)s - %(message)s',
            level=logging.DEBUG)

        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)


def main():
    Runner().main()


if __name__ == "__main__":
    main()
