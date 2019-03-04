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
import uuid

import requests
import voluptuous as vs
import yaml

import zuul.merger.merger
import zuul.lib.connections

from zuul.executor.common import JobDir, AnsibleJobBase, DeduplicateQueue
from zuul.executor.common import UpdateTask


class RunnerConfiguration(object):
    log = logging.getLogger("zuul.RunnerConfiguration")
    runner = {
        "job-dir": str,
        "git-dir": str,
    }

    schema = {
        'runner': runner,
        'api': str,
        'tenant': str,
        'project': str,
        'pipeline': str,
        'branch': str,
        'job': str,
    }

    def readConfig(self, config_path):
        config_path = os.path.expanduser(config_path)
        if os.path.exists(config_path):
            with open(config_path) as config_file:
                return yaml.safe_load(config_file)
        else:
            return {}

    def loadConfig(self, config, args=None):
        # Override from args
        if args:
            for key in self.schema:
                if getattr(args, key):
                    config[key] = args.key
        # Validate schema
        vs.Schema(self.schema)(config)
        # Set default value
        self.api = config["api"]
        self.tenant = config.get("tenant")
        self.pipeline = config.get("pipeline")
        self.project = config.get("project")
        self.branch = config.get("branch", "master")
        self.job = config.get("job")
        self.job_dir = config.get("runner", {}).get("job-dir")
        self.git_dir = config.get(
            "runner", {}).get("git-dir", "~/.cache/zuul/git")
        return config


class Runner(object):
    log = logging.getLogger("zuul.Runner")

    def __init__(self, config, connections={}):
        self.config = config
        self.connections = connections

    def _updateLoop(self):
        while True:
            try:
                if self._innerUpdateLoop():
                    break
            except Exception:
                self.log.exception("Exception in update thread:")

    def _innerUpdateLoop(self):
        # Inside of a loop that keeps the main repositories up to date
        task = self.update_queue.get()
        if task is None:
            # We are asked to stop
            return True
        try:
            with self.merger_lock:
                self.log.info("Updating repo %s/%s" % (
                    task.connection_name, task.project_name))
                self.merger.updateRepo(task.connection_name, task.project_name)
                repo = self.merger.getRepo(
                    task.connection_name, task.project_name)
                source = self.connections.getSource(task.connection_name)
                project = source.getProject(task.project_name)
                task.canonical_name = project.canonical_name
                task.branches = repo.getBranches()
                task.refs = [r.name for r in repo.getRefs()]
                self.log.debug("Finished updating repo %s/%s" %
                               (task.connection_name, task.project_name))
                task.success = True
        except Exception:
            self.log.exception('Got exception while updating repo %s/%s',
                               task.connection_name, task.project_name)
        finally:
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

    def _grab_frozen_job(self):
        url = self.config.api
        if self.config.tenant:
            url = os.path.join(url, "tenant", self.config.tenant)
        if self.config.project:
            url = os.path.join(
                url,
                "pipeline",
                self.config.pipeline,
                "project",
                self.config.project,
                "branch",
                self.config.branch,
                "freeze-job")
        if self.config.job:
            url = os.path.join(url, self.config.job)
        return requests.get(url).json()

    def prep_workspace(self):
        job_params = self._grab_frozen_job()
        self.library_dir = ""
        self.callback_dir = ""
        self.filter_dir = ""
        self.action_dir = ""
        self.lookup_dir = ""
        self.action_dir_general = ""
        self.merger_lock = threading.Lock()
        if self.config.job_dir:
            root = self.config.job_dir
            if root.endswith('/'):
                root = root[:-1]
            job_unique = root.split('/')[-1]
            root = os.path.dirname(root)
            os.makedirs(root, exist_ok=True)
        else:
            root = tempfile.mkdtemp()
            job_unique = str(uuid.uuid4().hex)
        job = AnsibleJobBase(self, job_params, job_unique)
        self.merge_root = os.path.expanduser(self.config.git_dir)
        self.merger = self._getMerger(self.merge_root)
        self.start_update_thread()
        # TODO(jhesketh):
        #  - Give options to clean up working dir
        job.jobdir = JobDir(root, keep=False, build_uuid=job_unique)
        job.prepareRepositories(self.update)
        job.preparePlaybooks(job_params)
        self.update_queue.put(None)
        self.update_thread.join()
        return job
