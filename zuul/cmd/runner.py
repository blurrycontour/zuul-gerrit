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
import tempfile
import threading
import sys
import uuid

import requests

import zuul.cmd
import zuul.merger.merger
import zuul.lib.connections

from zuul.executor.common import JobDir, AnsibleJobBase, DeduplicateQueue
from zuul.executor.common import UpdateTask


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
        parser.add_argument('-u', '--user',
                            help='the source connection user to merge changes')
        parser.add_argument('-k', '--key', default='~/.ssh/id_rsa',
                            help='the key to use for ssh connections')
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
        # Rebuild the connections necessary for the job.
        connections = zuul.lib.connections.ConnectionRegistry()

        if self.args.config:
            self.readConfig()
            connections.configure(self.config, source_only=True)
        else:
            # Query zuul-web endpoint
            url = os.path.join(self.args.api, "connections")
            conns = {}
            for config in requests.get(url).json():
                if self.args.user:
                    config['user'] = self.args.user
                config['sshkey'] = os.path.expanduser(self.args.key)
                conns[config['name']] = connections.drivers[
                    config['driver']].getConnection(config['name'], config)
            connections.connections = conns

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

    def _getMerger(self, root, cache_root=None, logger=None):
        email = 'todo'
        username = 'todo'
        speed_limit = '1000'
        speed_time = '1000'
        return zuul.merger.merger.Merger(
            root, self.connections, email, username,
            speed_limit, speed_time, cache_root, logger)

    def prep_workspace(self):
        job_params = self._grab_frozen_job()
        self.connections = self._constructConnections()
        self.library_dir = ""
        self.callback_dir = ""
        self.filter_dir = ""
        self.action_dir = ""
        self.lookup_dir = ""
        self.action_dir_general = ""
        self.merger_lock = threading.Lock()
        if self.args.dir:
            root = self.args.dir
            if root.endswith('/'):
                root = root[:-1]
            job_unique = root.split('/')[-1]
            root = os.path.dirname(root)
            os.makedirs(root, exist_ok=True)
        else:
            root = tempfile.mkdtemp()
            job_unique = str(uuid.uuid4().hex)
        job = AnsibleJobBase(self, job_params, job_unique)
        self.merge_root = os.path.expanduser(self.args.git_dir)
        self.merger = self._getMerger(self.merge_root)
        self.start_update_thread()
        # TODO(jhesketh):
        #  - Give options to clean up working dir
        #  - figure out what to do with build_uuid's
        job.jobdir = JobDir(root, keep=False, build_uuid=job_unique)
        job.prepareRepositories(self.update)
        job.preparePlaybooks(job_params)

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
