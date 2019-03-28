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
from concurrent.futures.process import ProcessPoolExecutor

import requests

import zuul
import zuul.merger.merger
import zuul.lib.connections
import zuul.lib.ansible

from zuul.executor.common import AnsibleJob
from zuul.executor.common import AnsibleJobContextManager
from zuul.executor.common import DeduplicateQueue
from zuul.executor.common import JobDir
from zuul.executor.common import UpdateTask


class LocalRunnerContextManager(AnsibleJobContextManager):
    """An object to manage running an AnsibleJob locally

    This ContextManager fetches the build parameters from a zuul's api
    freeze_job endpoint."""

    _job_class = AnsibleJob
    log = logging.getLogger("zuul.Runner")

    def __init__(self, runner_config, connections={}):
        super(LocalRunnerContextManager, self).__init__()
        self.runner_config = runner_config
        self.connections = connections
        self.ansible_manager = zuul.lib.ansible.AnsibleManager(
            runner_config["ansible-dir"])
        self.merge_root = os.path.expanduser(runner_config["git-dir"])
        self.merger_lock = threading.Lock()

        if self.runner_config["job-dir"]:
            root = self.runner_config["job-dir"]
            if root.endswith('/'):
                root = root[:-1]
            self.unique = root.split('/')[-1]
            root = os.path.dirname(root)
            os.makedirs(root, exist_ok=True)
        else:
            root = tempfile.mkdtemp()
            self.unique = str(uuid.uuid4().hex)

        self.ansible_job = self._job_class(
            self.unique,
            process_worker=ProcessPoolExecutor(),
            zuul_event_id="local",
            context_manager=self,
            getMerger=self.getMerger,
            merge_root=self.merge_root,
            connections=self.connections,
            ansible_manager=self.ansible_manager,
            execution_wrapper=self.connections.drivers["bubblewrap"],
            logger=self.log,
        )

        # TODO(jhesketh):
        #  - Give options to clean up working dir
        jobdir = JobDir(root, keep=False, build_uuid=self.unique)
        self.ansible_job.setJobDir(jobdir)

    def run(self):
        raise Exception("run is not implemented yet")

    def pause(self):
        self.log.warning(
            "Pausing is not supported by the local runner. "
            "The job will immediately continue.")

    def resume(self):
        pass

    def send_aborted(self):
        self.log.warning("Job is aborted")

    def stop(self):
        raise Exception("stop is not implemented yet")

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

    def update(self, connection_name, project_name,
               repo_state=None, zuul_event_id=None, build=None):
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

    def getMerger(self, root, cache_root=None, logger=None):
        email = 'todo'
        username = 'todo'
        speed_limit = '1000'
        speed_time = '1000'
        return zuul.merger.merger.Merger(
            root, self.connections, None, email, username,
            speed_limit, speed_time, cache_root, logger)

    def _grabFrozenJob(self):
        url = self.runner_config["api"]
        if self.runner_config.get("tenant"):
            url = os.path.join(url, "tenant", self.runner_config["tenant"])
        if self.runner_config.get("project"):
            url = os.path.join(
                url,
                "pipeline",
                self.runner_config["pipeline"],
                "project",
                self.runner_config["project"],
                "branch",
                self.runner_config["branch"],
                "freeze-job")
        if self.runner_config.get("job"):
            url = os.path.join(url, self.runner_config["job"])
        return requests.get(url).json()

    def prepareWorkspace(self):
        self.ansible_manager.copyAnsibleFiles()
        job_params = self._grabFrozenJob()

        self.merger = self.getMerger(self.merge_root)
        self.start_update_thread()

        self.ansible_job.prepareRepositories(self.update, job_params)
        self.ansible_job.preparePlaybooks(job_params)
        self.update_queue.put(None)
        self.update_thread.join()
