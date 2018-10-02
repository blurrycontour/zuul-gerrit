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
import tempfile
import threading
import sys

import zuul.cmd

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
        #  - Allow setting the zuul instance endpoint from params or env vars
        #  - Ditto tenant
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
        # TODO(jhesketh): grab from an endpoint
        inheritance_path = [
            '<Job base branches: None source: common-config/zuul.yaml'
            '@master#44>',
            '<Job project-test1 branches: None source: common-config/zuul.yaml'
            '@master#57>',
            '<Job project-test1 branches: None source: common-config/zuul.yaml'
            '@master#127>',
            '<Job project-test1 branches: None source: common-config/zuul.yaml'
            '@master#44>'
        ]

        job_params = {
            'job': 'project-test1',
            'timeout': None,
            'post_timeout': None,
            'items': [],
            'projects': [],
            'branch': 'master',
            'override_branch': None,
            'override_checkout': None,
            'repo_state': {},
            'playbooks': [{
                'connection': 'gerrit',
                'project': 'common-config',
                'branch': 'master',
                'trusted': True,
                'roles': [{
                    'target_name': 'common-config',
                    'type': 'zuul',
                    'project_canonical_name':
                        'review.example.com/common-config',
                    'implicit': True,
                    'project_default_branch': 'master',
                    'connection': 'gerrit',
                    'project': 'common-config',
                }],
                'secrets': {},
                'path': 'playbooks/project-test1.yaml',
            }],
            'pre_playbooks': [],
            'post_playbooks': [],
            'ssh_keys': [],
            'vars': {},
            'extra_vars': {},
            'host_vars': {},
            'group_vars': {},
            'zuul': {
                'build': '00000000000000000000000000000000',
                'buildset': None,
                'ref': None,
                'pipeline': 'check',
                'job': 'project-test1',
                'voting': True,
                'project': {
                    'name': 'org/project1',
                    'short_name': 'project1',
                    'canonical_hostname': 'review.example.com',
                    'canonical_name': 'review.example.com/org/project1',
                    'src_dir': 'src/review.example.com/org/project1',
                },
                'tenant': 'tenant-one',
                'timeout': None,
                'jobtags': [],
                '_inheritance_path': inheritance_path,
                'branch': 'master',
                'projects': {},
                'items': [],
                'child_jobs': [],
            },
        }

        return job_params

    def _constructConnections(self):
        # Rebuild the connections necessary for the job (specifically
        # getSource). This may involve querying the zuul server for public
        # attributes such as baseurl.
        
        # TODO
        return {}

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

    def _getMerger(self, root, cache_root, logger=None):
        # TODO
        return zuul.merger.merger.Merger(
            root, self.connections, self.merge_email, self.merge_name,
            self.merge_speed_limit, self.merge_speed_time, cache_root, logger,
            execution_context=True)

    def prep_workspace(self):
        self.connections = self._constructConnections()
        self.merge_root = tempfile.mkdtemp()
        self.merger = self._getMerger(self.merge_root, None)
        self.start_update_thread()
        job_params = self._grab_frozen_job()
        # TODO(jhesketh):
        #  - Allow working dir to be set
        #  - Give options to clean up working dir
        #  - figure out what to do with build_uuid's
        root = tempfile.mkdtemp()
        print("Working dir: %s" % root)
        self.jobdir = JobDir(root, keep=False, build_uuid="aaa")
        job = AnsibleJobBase(job_params, self.connections, self.merge_root)
        job.prepareRepositories(self.update)
        job.preparePlaybooks(job_params)

    def main(self):
        self.parseArguments()
        # self.setup_logging()

        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)


def main():
    Runner().main()


if __name__ == "__main__":
    main()
