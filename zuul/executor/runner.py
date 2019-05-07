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
import socket
import tempfile
import threading
import uuid
from concurrent.futures.process import ProcessPoolExecutor

import paramiko.transport
import requests
import voluptuous as vs
import yaml

import zuul
import zuul.merger.merger
import zuul.lib.connections
import zuul.lib.ansible

from zuul.executor.common import AnsibleJob
from zuul.executor.common import AnsibleJobContextManager
from zuul.executor.common import DeduplicateQueue
from zuul.executor.common import JobDir
from zuul.executor.common import UpdateTask
from zuul.executor.common import SshAgent


def get_host_key(node):
    addrinfo = socket.getaddrinfo(
        node["interface_ip"], node["connection_port"])[0]
    sock = socket.socket(addrinfo[0], socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(addrinfo[4])
    t = paramiko.transport.Transport(sock)
    t.start_client(timeout=10)
    key = t.get_remote_server_key()
    return "%s %s" % (key.get_name(), key.get_base64())


class RunnerConfiguration(object):
    node = {
        'label': str,
        'connection': str,
        'connection_port': int,
        'username': str,
        'hostname': str,
        'cwd': str,
    }

    schema = {
        'secrets': dict,
        'nodes': [node],
        "ansible-dir": str,
        "job-dir": str,
        "git-dir": str,
        "api": str,
        "tenant": str,
        "project": str,
        "pipeline": str,
        "branch": str,
        "job": str,
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
                key = str(key)
                args_key = key.replace('-', '_')
                if getattr(args, args_key, None):
                    config[key] = getattr(args, args_key)
        # Validate schema
        vs.Schema(self.schema)(config)
        # Set default value
        self.api = config["api"]
        self.tenant = config.get("tenant")
        self.pipeline = config.get("pipeline", "check")
        self.project = config.get("project")
        self.branch = config.get("branch", "master")
        self.job = config.get("job")
        self.job_dir = config.get("job-dir")
        self.ssh_key = config.get("ssh-key", "~/.ssh/id_rsa")
        self.ansible_dir = config.get("ansible-dir", "~/.cache/zuul/ansible")
        self.ansible_install_root = config.get(
            "ansible-bin", "~/.cache/zuul/ansible-bin")
        self.git_dir = config.get("git-dir", "~/.cache/zuul/git")
        self.nodes = config.get("nodes", [])
        self.secrets = config.get("secrets", {})
        return config


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
            os.path.expanduser(runner_config.ansible_dir),
            runtime_install_root=os.path.expanduser(
                runner_config.ansible_install_root))
        self.merge_root = os.path.expanduser(runner_config.git_dir)
        self.merger_lock = threading.Lock()

        if self.runner_config.job_dir:
            root = self.runner_config.job_dir
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
            # TODO(jhesketh): Fix getting ansible-version from job-params
            ansible_plugin_dir=self.ansible_manager.getAnsiblePluginDir(None),
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

    def grabFrozenJob(self):
        url = self.runner_config.api
        if self.runner_config.tenant:
            url = os.path.join(url, "tenant", self.runner_config.tenant)
        if self.runner_config.project:
            if not self.runner_config.pipeline:
                raise RuntimeError("You must specify a pipeline")
            if not self.runner_config.branch:
                raise RuntimeError("You must specify a branch")
            url = os.path.join(
                url,
                "pipeline",
                self.runner_config.pipeline,
                "project",
                self.runner_config.project,
                "branch",
                self.runner_config.branch,
                "freeze-job")
        if self.runner_config.job:
            url = os.path.join(url, self.runner_config.job)
        return requests.get(url).json()

    def prepareWorkspace(self, job_params):
        self.ansible_manager.copyAnsibleFiles()

        self.merger = self.getMerger(self.merge_root)
        self.start_update_thread()

        self.ansible_job.prepareRepositories(self.update, job_params)
        self.ansible_job.preparePlaybooks(job_params)
        self.update_queue.put(None)
        self.update_thread.join()

    def _setNodesAndSecrets(self, job_params):
        # Substitute nodeset with provided node
        local_nodes = self.runner_config.nodes
        if job_params["nodes"]:
            if len(local_nodes) != len(job_params["nodes"]):
                raise Exception("Not enough nodes provided to run %s" %
                                job_params["nodes"])

            for node in job_params["nodes"]:
                reserved_node = None
                for local_node in local_nodes:
                    if local_node.get("reserved"):
                        continue
                    if local_node.get("label") != node["label"]:
                        continue
                    reserved_node = local_node
                    local_node["reserved"] = True
                if reserved_node is None:
                    raise Exception("Couldn't find a local node for %s" %
                                    node)
                node["hostname"] = reserved_node["hostname"]
                node["interface_ip"] = socket.gethostbyname(node["hostname"])
                node["connection_type"] = reserved_node.get(
                    "connection", "ssh")
                node["connection_port"] = reserved_node.get(
                    "connection_port", 22)
                node["username"] = reserved_node.get("username", "zuul")
                node["cwd"] = reserved_node.get("cwd", "/home/zuul")
                if node["connection_type"] == "ssh":
                    node["host_keys"] = [get_host_key(node)]

        # Substitute secrets
        for playbook in (job_params["pre_playbooks"] +
                         job_params["playbooks"] +
                         job_params["post_playbooks"]):
            for secret in playbook["secrets"]:
                if secret not in self.runner_config.secrets:
                    self.log.warning("Secrets %s is unknown", secret)
                    # We can fake 'site_' secret with the provided node...
                    if secret.startswith("site_"):
                        node = job_params["nodes"][0]
                        self.runner_config.secrets[secret] = {
                            "fqdn": node["hostname"],
                            "path": os.path.join(node["cwd"], secret),
                            "ssh_username": node["username"],
                            "ssh_private_key": open(os.path.expanduser(
                                self.runner_config.ssh_key)).read(),
                        }
                        if node["connection_type"] == "ssh":
                            self.runner_config.secrets[secret][
                                "ssh_known_hosts"] = "%s %s" % (
                                    node["hostname"], get_host_key(node))
                playbook["secrets"][secret] = self.runner_config.secrets.get(
                    secret, "unknown")

    def execute(self, job_params, skip_ansible_install=False):
        self._setNodesAndSecrets(job_params)
        if not skip_ansible_install and not self.ansible_manager.validate():
            self.ansible_manager.install()
        self.prepareWorkspace(job_params)
        self.ansible_job.prepareAnsibleFiles(job_params)
        self.ansible_job.writeLoggingConfig()
        self.ssh_agent = SshAgent()
        result = None
        try:
            self.ssh_agent.start()
            # TODO: enable custom key
            self.ssh_agent.add(os.path.expanduser(self.runner_config.ssh_key))
            self.ansible_job.setExtraEnvVars(self.ssh_agent.env)
            result = self.ansible_job.runPlaybooks(job_params)
        finally:
            self.ssh_agent.stop()
        return result
