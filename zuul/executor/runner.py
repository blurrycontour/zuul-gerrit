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

import paramiko.transport
import requests
import voluptuous as vs
import yaml

import zuul
import zuul.merger.merger
import zuul.lib.connections
import zuul.lib.ansible

from zuul.executor.common import JobDir, AnsibleJob, DeduplicateQueue
from zuul.executor.common import UpdateTask, SshAgent


def get_host_key(node):
    addrinfo = socket.getaddrinfo(
        node["interface_ip"], node["connection_port"])[0]
    sock = socket.socket(addrinfo[0], socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(addrinfo[4])
    t = paramiko.transport.Transport(sock)
    t.start_client(timeout=10)
    key = t.get_remote_server_key()
    return "%s %s %s" % (node["hostname"], key.get_name(), key.get_base64())


class RunnerConfiguration(object):
    log = logging.getLogger("zuul.RunnerConfiguration")
    runner = {
        "ansible-dir": str,
        "job-dir": str,
        "git-dir": str,
        "ssh-key": str,
    }

    node = {
        'label': str,
        'connection': str,
        'connection_port': int,
        'username': str,
        'hostname': str,
        'cwd': str,
    }

    schema = {
        'runner': runner,
        'nodes': [node],
        'secrets': dict,
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
        config.setdefault("runner", {})
        # Override from args
        if args:
            for key in self.schema:
                if getattr(args, key):
                    config[key] = args.key
            if args.directory:
                config["runner"]["job-dir"] = args.directory
            if args.git_dir:
                config["runner"]["git-dir"] = args.git_dir
            if args.key:
                config["runner"]["ssh-key"] = args.key
        # Validate schema
        vs.Schema(self.schema)(config)
        # Set default value
        self.api = config["api"]
        self.tenant = config.get("tenant")
        self.pipeline = config.get("pipeline")
        self.project = config.get("project")
        self.branch = config.get("branch", "master")
        self.job = config.get("job")
        self.job_dir = config["runner"].get("job-dir")
        self.ansible_dir = config["runner"].get(
            "ansible-dir", "~/.cache/zuul/ansible")
        self.git_dir = config["runner"].get("git-dir", "~/.cache/zuul/git")
        self.ssh_key = config["runner"].get("ssh-key", "~/.ssh/id_rsa")
        self.nodes = config.get("nodes", [])
        self.secrets = config.get("secrets", {})
        return config


class Runner(object):
    log = logging.getLogger("zuul.Runner")

    def __init__(self, runner_config, connections={}):
        self.runner_config = runner_config
        self.connections = connections
        self.ansible_manager = zuul.lib.ansible.AnsibleManager(
            runner_config.ansible_dir)
        self.merge_root = os.path.expanduser(self.runner_config.git_dir)
        self.job_params = None

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

    def getMerger(self, root, cache_root=None, logger=None):
        email = 'todo'
        username = 'todo'
        speed_limit = '1000'
        speed_time = '1000'
        return zuul.merger.merger.Merger(
            root, self.connections, email, username,
            speed_limit, speed_time, cache_root, logger)

    def _grabFrozenJob(self):
        url = self.runner_config.api
        if self.runner_config.tenant:
            url = os.path.join(url, "tenant", self.runner_config.tenant)
        if self.runner_config.project:
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
        self.job_params = requests.get(url).json()

        # Substitute nodeset with provided node
        local_nodes = self.runner_config.nodes
        if self.job_params["nodes"]:
            if len(local_nodes) != len(self.job_params["nodes"]):
                raise Exception("Not enough nodes provided to run %s" %
                                self.job_params["nodes"])

            for node in self.job_params["nodes"]:
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

        # Substitute secrets
        for playbook in (self.job_params["pre_playbooks"] +
                         self.job_params["playbooks"] +
                         self.job_params["post_playbooks"]):
            for secret in playbook["secrets"]:
                if secret not in self.runner_config.secrets:
                    self.log.warning("Secrets %s is unknown", secret)
                    # We can fake 'site_' secret with the provided node...
                    if secret.startswith("site_"):
                        node = self.job_params["nodes"][0]
                        self.runner_config.secrets[secret] = {
                            "fqdn": node["hostname"],
                            "path": os.path.join(node["cwd"], secret),
                            "ssh_username": node["username"],
                            "ssh_private_key": open(os.path.expanduser(
                                self.config.key)).read(),
                        }
                        if node["connection_type"] == "ssh":
                            self.runner_config.secrets[secret][
                                "ssh_known_hosts"] = get_host_key(node)
                playbook["secrets"][secret] = self.runner_config.secrets.get(
                    secret, "unknown")

        return self.job_params

    def prepareWorkspace(self):
        self.ansible_manager.copyAnsibleFiles()
        job_params = self._grabFrozenJob()
        self.merger_lock = threading.Lock()
        if self.runner_config.job_dir:
            root = self.runner_config.job_dir
            if root.endswith('/'):
                root = root[:-1]
            job_unique = root.split('/')[-1]
            root = os.path.dirname(root)
            os.makedirs(root, exist_ok=True)
        else:
            root = tempfile.mkdtemp()
            job_unique = str(uuid.uuid4().hex)
        job = AnsibleJob(
            job_params,
            job_unique,
            self.getMerger,
            merge_root=self.merge_root,
            connections=self.connections,
            ansible_manager=self.ansible_manager,
            execution_wrapper=self.connections.drivers["bubblewrap"])
        ansible_lib = self.ansible_manager.getAnsiblePluginDir(
            job_params.get('ansible_version'))
        job.library_dir = os.path.join(ansible_lib, "library")
        job.callback_dir = os.path.join(ansible_lib, "callback")
        job.filter_dir = os.path.join(ansible_lib, "filter")
        job.action_dir = os.path.join(ansible_lib, "action")
        job.lookup_dir = os.path.join(ansible_lib, "lookup")
        job.action_dir_general = os.path.join(ansible_lib, "actiongeneral")
        job.ansible_dir = ansible_lib

        self.merger = self.getMerger(self.merge_root)
        self.start_update_thread()
        # TODO(jhesketh):
        #  - Give options to clean up working dir
        job.jobdir = JobDir(root, keep=False, build_uuid=job_unique)
        job.prepareRepositories(self.update)
        job.preparePlaybooks(job_params)
        job.prepareAnsibleFiles(job_params)
        job.writeLoggingConfig()
        self.update_queue.put(None)
        self.update_thread.join()
        return job

    def execute(self, job):
        job.ssh_agent = SshAgent()
        try:
            job.ssh_agent.start()
            # TODO: enable custom key
            job.ssh_agent.add(os.path.expanduser(self.runner_config.ssh_key))
            return job.runPlaybooks(self.job_params)
        finally:
            job.ssh_agent.stop()
