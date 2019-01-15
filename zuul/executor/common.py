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

import collections
import datetime
import json
import logging
import os
import tempfile
import signal
import shutil
import shlex
import subprocess
import threading
import time
import traceback
import git
from urllib.parse import urlsplit

import zuul.ansible.logconfig
import zuul.merger.merger

from zuul.lib.config import get_default
from zuul.lib.yamlutil import yaml
from zuul.lib import filecomments

try:
    import ara.plugins.callbacks as ara_callbacks
except ImportError:
    ara_callbacks = None

BUFFER_LINES_FOR_SYNTAX = 200
DEFAULT_FINGER_PORT = 7900
BLACKLISTED_ANSIBLE_CONNECTION_TYPES = [
    'network_cli', 'kubectl', 'project', 'namespace']


def check_varnames(var):
    # We block these in configloader, but block it here too to make
    # sure that a job doesn't pass variables named zuul or nodepool.
    if 'zuul' in var:
        raise Exception("Defining variables named 'zuul' is not allowed")
    if 'nodepool' in var:
        raise Exception("Defining variables named 'nodepool' is not allowed")


def make_setup_inventory_dict(nodes):
    hosts = {}
    for node in nodes:
        if (node['host_vars']['ansible_connection'] in
            BLACKLISTED_ANSIBLE_CONNECTION_TYPES):
            continue
        hosts[node['name']] = node['host_vars']

    inventory = {
        'all': {
            'hosts': hosts,
        }
    }

    return inventory


def make_inventory_dict(nodes, args, all_vars):
    hosts = {}
    for node in nodes:
        hosts[node['name']] = node['host_vars']

    inventory = {
        'all': {
            'hosts': hosts,
            'vars': all_vars,
        }
    }

    for group in args['groups']:
        if 'children' not in inventory['all']:
            inventory['all']['children'] = dict()
        group_hosts = {}
        for node_name in group['nodes']:
            group_hosts[node_name] = None
        group_vars = args['group_vars'].get(group['name'], {}).copy()
        check_varnames(group_vars)

        inventory['all']['children'].update({
            group['name']: {
                'hosts': group_hosts,
                'vars': group_vars,
            }})

    return inventory


class UpdateTask(object):
    def __init__(self, connection_name, project_name):
        self.connection_name = connection_name
        self.project_name = project_name
        self.canonical_name = None
        self.branches = None
        self.refs = None
        self.event = threading.Event()

    def __eq__(self, other):
        if (other and other.connection_name == self.connection_name and
            other.project_name == self.project_name):
            return True
        return False

    def wait(self):
        self.event.wait()

    def setComplete(self):
        self.event.set()


class DeduplicateQueue(object):
    def __init__(self):
        self.queue = collections.deque()
        self.condition = threading.Condition()

    def qsize(self):
        return len(self.queue)

    def put(self, item):
        # Returns the original item if added, or an equivalent item if
        # already enqueued.
        self.condition.acquire()
        ret = None
        try:
            for x in self.queue:
                if item == x:
                    ret = x
            if ret is None:
                ret = item
                self.queue.append(item)
                self.condition.notify()
        finally:
            self.condition.release()
        return ret

    def get(self):
        self.condition.acquire()
        try:
            while True:
                try:
                    ret = self.queue.popleft()
                    return ret
                except IndexError:
                    pass
                self.condition.wait()
        finally:
            self.condition.release()


class Watchdog(object):
    def __init__(self, timeout, function, args):
        self.timeout = timeout
        self.function = function
        self.args = args
        self.thread = threading.Thread(target=self._run,
                                       name='watchdog')
        self.thread.daemon = True
        self.timed_out = None

    def _run(self):
        while self._running and time.time() < self.end:
            time.sleep(10)
        if self._running:
            self.timed_out = True
            self.function(*self.args)
        else:
            # Only set timed_out to false if we aren't _running
            # anymore. This means that we stopped running not because
            # of a timeout but because normal execution ended.
            self.timed_out = False

    def start(self):
        self._running = True
        self.end = time.time() + self.timeout
        self.thread.start()

    def stop(self):
        self._running = False


class ExecutorError(Exception):
    """A non-transient run-time executor error

    This class represents error conditions detected by the executor
    when preparing to run a job which we know are consistently fatal.
    Zuul should not reschedule the build in these cases.
    """
    pass


class RoleNotFoundError(ExecutorError):
    pass


class JobDirPlaybook(object):
    def __init__(self, root, exist_ok=False):
        self.root = root
        self.trusted = None
        self.project_canonical_name = None
        self.branch = None
        self.canonical_name_and_path = None
        self.path = None
        self.roles = []
        self.roles_path = []
        self.ansible_config = os.path.join(self.root, 'ansible.cfg')
        self.project_link = os.path.join(self.root, 'project')
        self.secrets_root = os.path.join(self.root, 'secrets')
        os.makedirs(self.secrets_root, exist_ok=exist_ok)
        self.secrets = os.path.join(self.secrets_root, 'secrets.yaml')
        self.secrets_content = None

    def addRole(self):
        count = len(self.roles)
        root = os.path.join(self.root, 'role_%i' % (count,))
        os.makedirs(root)
        self.roles.append(root)
        return root


class JobDir(object):
    def __init__(self, root, keep, build_uuid, exist_ok=False):
        '''
        :param str root: Root directory for the individual job directories.
            Can be None to use the default system temp root directory.
        :param bool keep: If True, do not delete the job directory.
        :param str build_uuid: The unique build UUID. If supplied, this will
            be used as the temp job directory name. Using this will help the
            log streaming daemon find job logs.
        '''
        # root
        #   ansible (mounted in bwrap read-only)
        #     logging.json
        #     inventory.yaml
        #     extra_vars.yaml
        #   .ansible (mounted in bwrap read-write)
        #     fact-cache/localhost
        #     cp
        #   playbook_0 (mounted in bwrap for each playbook read-only)
        #     secrets.yaml
        #     project -> ../trusted/project_0/...
        #     role_0 -> ../trusted/project_0/...
        #   trusted (mounted in bwrap read-only)
        #     project_0
        #       <git.example.com>
        #         <project>
        #   untrusted (mounted in bwrap read-only)
        #     project_0
        #       <git.example.com>
        #         <project>
        #   work (mounted in bwrap read-write)
        #     .ssh
        #       known_hosts
        #     src
        #       <git.example.com>
        #         <project>
        #     logs
        #       job-output.txt
        #     tmp
        #     results.json
        self.keep = keep
        if root:
            tmpdir = root
        else:
            tmpdir = tempfile.gettempdir()
        self.root = os.path.join(tmpdir, build_uuid)
        os.makedirs(self.root, 0o700, exist_ok=exist_ok)
        self.work_root = os.path.join(self.root, 'work')
        os.makedirs(self.work_root, exist_ok=exist_ok)
        self.src_root = os.path.join(self.work_root, 'src')
        os.makedirs(self.src_root, exist_ok=exist_ok)
        self.log_root = os.path.join(self.work_root, 'logs')
        os.makedirs(self.log_root, exist_ok=exist_ok)
        # Create local tmp directory
        # NOTE(tobiash): This must live within the work root as it can be used
        # by ansible for temporary files which are path checked in untrusted
        # jobs.
        self.local_tmp = os.path.join(self.work_root, 'tmp')
        os.makedirs(self.local_tmp, exist_ok=exist_ok)
        self.ansible_root = os.path.join(self.root, 'ansible')
        os.makedirs(self.ansible_root, exist_ok=exist_ok)
        self.trusted_root = os.path.join(self.root, 'trusted')
        os.makedirs(self.trusted_root, exist_ok=exist_ok)
        self.untrusted_root = os.path.join(self.root, 'untrusted')
        os.makedirs(self.untrusted_root, exist_ok=exist_ok)
        ssh_dir = os.path.join(self.work_root, '.ssh')
        os.makedirs(ssh_dir, 0o700, exist_ok=exist_ok)
        # Create ansible cache directory
        self.ansible_cache_root = os.path.join(self.root, '.ansible')
        self.fact_cache = os.path.join(self.ansible_cache_root, 'fact-cache')
        os.makedirs(self.fact_cache, exist_ok=exist_ok)
        self.control_path = os.path.join(self.ansible_cache_root, 'cp')
        self.job_unreachable_file = os.path.join(self.ansible_cache_root,
                                                 'nodes.unreachable')
        os.makedirs(self.control_path, exist_ok=exist_ok)
        localhost_facts = os.path.join(self.fact_cache, 'localhost')
        # NOTE(pabelanger): We do not want to leak zuul-executor facts to other
        # playbooks now that smart fact gathering is enabled by default.  We
        # can have ansible skip populating the cache with information by the
        # doing the following.
        with open(localhost_facts, 'w') as f:
            f.write('{"module_setup": true}')

        self.result_data_file = os.path.join(self.work_root, 'results.json')
        with open(self.result_data_file, 'w'):
            pass
        self.known_hosts = os.path.join(ssh_dir, 'known_hosts')
        self.inventory = os.path.join(self.ansible_root, 'inventory.yaml')
        self.extra_vars = os.path.join(self.ansible_root, 'extra_vars.yaml')
        self.setup_inventory = os.path.join(self.ansible_root,
                                            'setup-inventory.yaml')
        self.logging_json = os.path.join(self.ansible_root, 'logging.json')
        self.playbooks = []  # The list of candidate playbooks
        self.playbook = None  # A pointer to the candidate we have chosen
        self.pre_playbooks = []
        self.post_playbooks = []
        self.job_output_file = os.path.join(self.log_root, 'job-output.txt')
        # We need to create the job-output.txt upfront in order to close the
        # gap between url reporting and ansible creating the file. Otherwise
        # there is a period of time where the user can click on the live log
        # link on the status page but the log streaming fails because the file
        # is not there yet.
        with open(self.job_output_file, 'w') as job_output:
            job_output.write("{now} | Job console starting...\n".format(
                now=datetime.datetime.now()
            ))
        self.trusted_projects = []
        self.trusted_project_index = {}
        self.untrusted_projects = []
        self.untrusted_project_index = {}

        # Create a JobDirPlaybook for the Ansible setup run.  This
        # doesn't use an actual playbook, but it lets us use the same
        # methods to write an ansible.cfg as the rest of the Ansible
        # runs.
        setup_root = os.path.join(self.ansible_root, 'setup_playbook')
        os.makedirs(setup_root, exist_ok=exist_ok)
        self.setup_playbook = JobDirPlaybook(setup_root, exist_ok)
        self.setup_playbook.trusted = True

    def addTrustedProject(self, canonical_name, branch):
        # Trusted projects are placed in their own directories so that
        # we can support using different branches of the same project
        # in different playbooks.
        count = len(self.trusted_projects)
        root = os.path.join(self.trusted_root, 'project_%i' % (count,))
        os.makedirs(root)
        self.trusted_projects.append(root)
        self.trusted_project_index[(canonical_name, branch)] = root
        return root

    def getTrustedProject(self, canonical_name, branch):
        return self.trusted_project_index.get((canonical_name, branch))

    def addUntrustedProject(self, canonical_name, branch):
        # Similar to trusted projects, but these hold checkouts of
        # projects which are allowed to have speculative changes
        # applied.  They might, however, be different branches than
        # what is used in the working dir, so they need their own
        # location.  Moreover, we might avoid mischief if a job alters
        # the contents of the working dir.
        count = len(self.untrusted_projects)
        root = os.path.join(self.untrusted_root, 'project_%i' % (count,))
        os.makedirs(root)
        self.untrusted_projects.append(root)
        self.untrusted_project_index[(canonical_name, branch)] = root
        return root

    def getUntrustedProject(self, canonical_name, branch):
        return self.untrusted_project_index.get((canonical_name, branch))

    def addPrePlaybook(self):
        count = len(self.pre_playbooks)
        root = os.path.join(self.ansible_root, 'pre_playbook_%i' % (count,))
        os.makedirs(root)
        playbook = JobDirPlaybook(root)
        self.pre_playbooks.append(playbook)
        return playbook

    def addPostPlaybook(self):
        count = len(self.post_playbooks)
        root = os.path.join(self.ansible_root, 'post_playbook_%i' % (count,))
        os.makedirs(root)
        playbook = JobDirPlaybook(root)
        self.post_playbooks.append(playbook)
        return playbook

    def addPlaybook(self):
        count = len(self.playbooks)
        root = os.path.join(self.ansible_root, 'playbook_%i' % (count,))
        os.makedirs(root)
        playbook = JobDirPlaybook(root)
        self.playbooks.append(playbook)
        return playbook

    def cleanup(self):
        if not self.keep:
            shutil.rmtree(self.root)

    def __enter__(self):
        return self

    def __exit__(self, etype, value, tb):
        self.cleanup()


class SshAgent(object):
    log = logging.getLogger("zuul.ExecutorServer")

    def __init__(self):
        self.env = {}
        self.ssh_agent = None

    def start(self):
        if self.ssh_agent:
            return
        with open('/dev/null', 'r+') as devnull:
            ssh_agent = subprocess.Popen(['ssh-agent'], close_fds=True,
                                         stdout=subprocess.PIPE,
                                         stderr=devnull,
                                         stdin=devnull)
        (output, _) = ssh_agent.communicate()
        output = output.decode('utf8')
        for line in output.split("\n"):
            if '=' in line:
                line = line.split(";", 1)[0]
                (key, value) = line.split('=')
                self.env[key] = value
        self.log.info('Started SSH Agent, {}'.format(self.env))

    def stop(self):
        if 'SSH_AGENT_PID' in self.env:
            try:
                os.kill(int(self.env['SSH_AGENT_PID']), signal.SIGTERM)
            except OSError:
                self.log.exception(
                    'Problem sending SIGTERM to agent {}'.format(self.env))
            self.log.debug('Sent SIGTERM to SSH Agent, {}'.format(self.env))
            self.env = {}

    def add(self, key_path):
        env = os.environ.copy()
        env.update(self.env)
        key_path = os.path.expanduser(key_path)
        self.log.debug('Adding SSH Key {}'.format(key_path))
        try:
            subprocess.check_output(['ssh-add', key_path], env=env,
                                    stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            self.log.exception('ssh-add failed. stdout: %s, stderr: %s',
                               e.output, e.stderr)
            raise
        self.log.info('Added SSH Key {}'.format(key_path))

    def addData(self, name, key_data):
        env = os.environ.copy()
        env.update(self.env)
        self.log.debug('Adding SSH Key {}'.format(name))
        try:
            subprocess.check_output(['ssh-add', '-'], env=env,
                                    input=key_data.encode('utf8'),
                                    stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            self.log.exception('ssh-add failed. stdout: %s, stderr: %s',
                               e.output, e.stderr)
            raise
        self.log.info('Added SSH Key {}'.format(name))

    def remove(self, key_path):
        env = os.environ.copy()
        env.update(self.env)
        key_path = os.path.expanduser(key_path)
        self.log.debug('Removing SSH Key {}'.format(key_path))
        subprocess.check_output(['ssh-add', '-d', key_path], env=env,
                                stderr=subprocess.PIPE)
        self.log.info('Removed SSH Key {}'.format(key_path))

    def list(self):
        if 'SSH_AUTH_SOCK' not in self.env:
            return None
        env = os.environ.copy()
        env.update(self.env)
        result = []
        for line in subprocess.Popen(['ssh-add', '-L'], env=env,
                                     stdout=subprocess.PIPE).stdout:
            line = line.decode('utf8')
            if line.strip() == 'The agent has no identities.':
                break
            result.append(line.strip())
        return result


class AnsibleJobLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        msg, kwargs = super(AnsibleJobLogAdapter, self).process(msg, kwargs)
        msg = '[build: %s] %s' % (kwargs['extra']['job'], msg)
        return msg, kwargs


class AnsibleJobBase(object):
    "This class prepares the roles and repositories for an Ansible Job"

    RESULT_NORMAL = 1
    RESULT_TIMED_OUT = 2
    RESULT_UNREACHABLE = 3
    RESULT_ABORTED = 4
    RESULT_DISK_FULL = 5

    RESULT_MAP = {
        RESULT_NORMAL: 'RESULT_NORMAL',
        RESULT_TIMED_OUT: 'RESULT_TIMED_OUT',
        RESULT_UNREACHABLE: 'RESULT_UNREACHABLE',
        RESULT_ABORTED: 'RESULT_ABORTED',
        RESULT_DISK_FULL: 'RESULT_DISK_FULL',
    }

    def __init__(self, job_runner, arguments):
        self.log = logging.getLogger("zuul.AnsibleJobBase")
        self.arguments = arguments
        self.jobdir = None
        self.project_info = {}
        self.executor_server = job_runner
        self.executor_variables_file = None
        self.connections = job_runner.connections
        self.merge_root = job_runner.merge_root
        self.ansible_dir = None
        self.proc_lock = threading.Lock()
        self.aborted = False
        self.cpu_times = {'user': 0, 'system': 0,
                          'children_user': 0, 'children_system': 0}

    def writeAnsibleConfig(self, jobdir_playbook):
        with open(jobdir_playbook.ansible_config, 'w') as config:
            config.write('[defaults]\n')
            config.write('inventory = %s\n' % self.jobdir.inventory)
            config.write('local_tmp = %s\n' % self.jobdir.local_tmp)
            config.write('retry_files_enabled = False\n')
            config.write('gathering = smart\n')
            config.write('fact_caching = jsonfile\n')
            config.write('fact_caching_connection = %s\n' %
                         self.jobdir.fact_cache)
            if self.executor_server:
                config.write('stdout_callback = zuul_stream\n')
                config.write('library = %s\n'
                             % self.executor_server.library_dir)
                config.write('callback_plugins = %s\n'
                             % self.executor_server.callback_dir)
                config.write('filter_plugins = %s\n'
                             % self.executor_server.filter_dir)

            config.write('command_warnings = False\n')

            if jobdir_playbook.roles_path:
                config.write('roles_path = %s\n' % ':'.join(
                    jobdir_playbook.roles_path))

    def getMerger(
            self, root, cache_root=None, logger=None, execution_context=None):
        # TODO(jhesketh): Maybe return a merger directly here
        email = 'todo'
        username = 'todo'
        speed_limit = '1000'
        speed_time = '1000'
        return zuul.merger.merger.Merger(
            root, self.connections, email, username,
            speed_limit, speed_time, cache_root, logger)

    def resolveBranch(self, project_canonical_name, ref, zuul_branch,
                      job_override_branch, job_override_checkout,
                      project_override_branch, project_override_checkout,
                      project_default_branch):
        branches = self.project_info[project_canonical_name]['branches']
        refs = self.project_info[project_canonical_name]['refs']
        selected_ref = None
        selected_desc = None
        if project_override_checkout in refs:
            selected_ref = project_override_checkout
            selected_desc = 'project override ref'
        elif project_override_branch in branches:
            selected_ref = project_override_branch
            selected_desc = 'project override branch'
        elif job_override_checkout in refs:
            selected_ref = job_override_checkout
            selected_desc = 'job override ref'
        elif job_override_branch in branches:
            selected_ref = job_override_branch
            selected_desc = 'job override branch'
        elif ref and ref.startswith('refs/heads/'):
            selected_ref = ref[len('refs/heads/'):]
            selected_desc = 'branch ref'
        elif ref and ref.startswith('refs/tags/'):
            selected_ref = ref[len('refs/tags/'):]
            selected_desc = 'tag ref'
        elif zuul_branch and zuul_branch in branches:
            selected_ref = zuul_branch
            selected_desc = 'zuul branch'
        elif project_default_branch in branches:
            selected_ref = project_default_branch
            selected_desc = 'project default branch'
        else:
            raise ExecutorError("Project %s does not have the "
                                "default branch %s" %
                                (project_canonical_name,
                                 project_default_branch))
        return (selected_ref, selected_desc)

    def findPlaybook(self, path, trusted=False):
        if os.path.exists(path):
            if not trusted:
                # Plugins can be defined in multiple locations within the
                # playbook's subtree.
                #
                #  1. directly within the playbook:
                #       block playbook_dir/*_plugins
                #
                #  2. within a role defined in playbook_dir/<rolename>:
                #       block playbook_dir/*/*_plugins
                #
                #  3. within a role defined in playbook_dir/roles/<rolename>:
                #       block playbook_dir/roles/*/*_plugins

                playbook_dir = os.path.dirname(os.path.abspath(path))
                paths_to_check = []

                def addPathsToCheck(root_dir):
                    if os.path.isdir(root_dir):
                        for entry in os.listdir(root_dir):
                            entry = os.path.join(root_dir, entry)
                            if os.path.isdir(entry):
                                paths_to_check.append(entry)

                # handle case 1
                paths_to_check.append(playbook_dir)

                # handle case 2
                addPathsToCheck(playbook_dir)

                # handle case 3
                addPathsToCheck(os.path.join(playbook_dir, 'roles'))

                for path_to_check in paths_to_check:
                    self._blockPluginDirs(path_to_check)

            return path
        raise ExecutorError("Unable to find playbook %s" % path)

    def preparePlaybooks(self, args):
        self.writeAnsibleConfig(self.jobdir.setup_playbook)

        for playbook in args['pre_playbooks']:
            jobdir_playbook = self.jobdir.addPrePlaybook()
            self.preparePlaybook(jobdir_playbook, playbook, args)

        for playbook in args['playbooks']:
            jobdir_playbook = self.jobdir.addPlaybook()
            self.preparePlaybook(jobdir_playbook, playbook, args)
            if jobdir_playbook.path is not None:
                self.jobdir.playbook = jobdir_playbook
                break

        if self.jobdir.playbook is None:
            raise ExecutorError("No playbook specified")

        for playbook in args['post_playbooks']:
            jobdir_playbook = self.jobdir.addPostPlaybook()
            self.preparePlaybook(jobdir_playbook, playbook, args)

    def preparePlaybook(self, jobdir_playbook, playbook, args):
        # Check out the playbook repo if needed and set the path to
        # the playbook that should be run.
        self.log.debug("Prepare playbook repo for %s: %s@%s" %
                       (playbook['trusted'] and 'trusted' or 'untrusted',
                        playbook['project'], playbook['branch']))
        source = self.connections.getSource(
            playbook['connection'])
        project = source.getProject(playbook['project'])
        branch = playbook['branch']
        jobdir_playbook.trusted = playbook['trusted']
        jobdir_playbook.branch = branch
        jobdir_playbook.project_canonical_name = project.canonical_name
        jobdir_playbook.canonical_name_and_path = os.path.join(
            project.canonical_name, playbook['path'])
        path = None

        if not jobdir_playbook.trusted:
            path = self.checkoutUntrustedProject(project, branch, args)
        else:
            path = self.checkoutTrustedProject(project, branch)
        path = os.path.join(path, playbook['path'])

        jobdir_playbook.path = self.findPlaybook(
            path,
            trusted=jobdir_playbook.trusted)

        # If this playbook doesn't exist, don't bother preparing
        # roles.
        if not jobdir_playbook.path:
            return

        for role in playbook['roles']:
            self.prepareRole(jobdir_playbook, role, args)

        secrets = playbook['secrets']
        if secrets:
            check_varnames(secrets)
            jobdir_playbook.secrets_content = yaml.safe_dump(
                secrets, default_flow_style=False)

        self.writeAnsibleConfig(jobdir_playbook)

    def checkoutTrustedProject(self, project, branch):
        root = self.jobdir.getTrustedProject(project.canonical_name,
                                             branch)
        if not root:
            root = self.jobdir.addTrustedProject(project.canonical_name,
                                                 branch)
            self.log.debug("Cloning %s@%s into new trusted space %s",
                           project, branch, root)
            merger = self.getMerger(
                root,
                self.merge_root,
                self.log)
            merger.checkoutBranch(project.connection_name, project.name,
                                  branch)
        else:
            self.log.debug("Using existing repo %s@%s in trusted space %s",
                           project, branch, root)

        path = os.path.join(root,
                            project.canonical_hostname,
                            project.name)
        return path

    def checkoutUntrustedProject(self, project, branch, args):
        root = self.jobdir.getUntrustedProject(project.canonical_name,
                                               branch)
        if not root:
            root = self.jobdir.addUntrustedProject(project.canonical_name,
                                                   branch)
            # If the project is in the dependency chain, clone from
            # there so we pick up any speculative changes, otherwise,
            # clone from the cache.
            merger = None
            for p in args['projects']:
                if (p['connection'] == project.connection_name and
                    p['name'] == project.name):
                    # We already have this repo prepared
                    self.log.debug("Found workdir repo for untrusted project")
                    # NOTE(tristanC): only valid for executor server context
                    merger = self.executor_server._getMerger(
                        root,
                        self.jobdir.src_root,
                        self.log)
                    break

            if merger is None:
                merger = self.getMerger(
                    root,
                    self.merge_root,
                    self.log)

            self.log.debug("Cloning %s@%s into new untrusted space %s",
                           project, branch, root)
            merger.checkoutBranch(project.connection_name, project.name,
                                  branch)
        else:
            self.log.debug("Using existing repo %s@%s in trusted space %s",
                           project, branch, root)

        path = os.path.join(root,
                            project.canonical_hostname,
                            project.name)
        return path

    def prepareRole(self, jobdir_playbook, role, args):
        if role['type'] == 'zuul':
            root = jobdir_playbook.addRole()
            self.prepareZuulRole(jobdir_playbook, role, args, root)

    def findRole(self, path, trusted=False):
        d = os.path.join(path, 'tasks')
        if os.path.isdir(d):
            # This is a bare role
            if not trusted:
                self._blockPluginDirs(path)
            # None signifies that the repo is a bare role
            return None
        d = os.path.join(path, 'roles')
        if os.path.isdir(d):
            # This repo has a collection of roles
            if not trusted:
                self._blockPluginDirs(d)
                for entry in os.listdir(d):
                    entry_path = os.path.join(d, entry)
                    if os.path.isdir(entry_path):
                        self._blockPluginDirs(entry_path)
            return d
        # It is neither a bare role, nor a collection of roles
        raise RoleNotFoundError("Unable to find role in %s" % (path,))

    def prepareZuulRole(self, jobdir_playbook, role, args, root):
        self.log.debug("Prepare zuul role for %s" % (role,))
        # Check out the role repo if needed
        source = self.connections.getSource(
            role['connection'])
        project = source.getProject(role['project'])
        name = role['target_name']
        path = None

        # Find the branch to use for this role.  We should generally
        # follow the normal fallback procedure, unless this role's
        # project is the playbook's project, in which case we should
        # use the playbook branch.
        if jobdir_playbook.project_canonical_name == project.canonical_name:
            branch = jobdir_playbook.branch
            self.log.debug("Role project is playbook project, "
                           "using playbook branch %s", branch)
        else:
            # Find if the project is one of the job-specified projects.
            # If it is, we can honor the project checkout-override options.
            args_project = {}
            for p in args['projects']:
                if (p['canonical_name'] == project.canonical_name):
                    args_project = p
                    break

            branch, selected_desc = self.resolveBranch(
                project.canonical_name,
                None,
                args['branch'],
                args['override_branch'],
                args['override_checkout'],
                args_project.get('override_branch'),
                args_project.get('override_checkout'),
                role['project_default_branch'])
            self.log.debug("Role using %s %s", selected_desc, branch)

        if not jobdir_playbook.trusted:
            path = self.checkoutUntrustedProject(project, branch, args)
        else:
            path = self.checkoutTrustedProject(project, branch)

        # The name of the symlink is the requested name of the role
        # (which may be the repo name or may be something else; this
        # can come into play if this is a bare role).
        link = os.path.join(root, name)
        link = os.path.realpath(link)
        if not link.startswith(os.path.realpath(root)):
            raise ExecutorError("Invalid role name %s", name)
        os.symlink(path, link)

        try:
            role_path = self.findRole(link, trusted=jobdir_playbook.trusted)
        except RoleNotFoundError:
            if role['implicit']:
                self.log.debug("Implicit role not found in %s", link)
                return
            raise
        if role_path is None:
            # In the case of a bare role, add the containing directory
            role_path = root
        self.log.debug("Adding role path %s", role_path)
        jobdir_playbook.roles_path.append(role_path)

    def prepareRepositories(self, update_manager, exists_ok=True):
        args = self.arguments
        tasks = []
        projects = set()

        # Make sure all projects used by the job are updated...
        for project in args['projects']:
            self.log.debug("Updating project %s" % (project,))
            tasks.append(update_manager(
                project['connection'], project['name']))
            projects.add((project['connection'], project['name']))

        # ...as well as all playbook and role projects.
        repos = []
        playbooks = (args['pre_playbooks'] + args['playbooks'] +
                     args['post_playbooks'])
        for playbook in playbooks:
            repos.append(playbook)
            repos += playbook['roles']

        for repo in repos:
            self.log.debug("Updating playbook or role %s" % (repo['project'],))
            key = (repo['connection'], repo['project'])
            if key not in projects:
                tasks.append(update_manager(*key))
                projects.add(key)

        for task in tasks:
            task.wait()
            self.project_info[task.canonical_name] = {
                'refs': task.refs,
                'branches': task.branches,
            }

        self.log.debug("Git updates complete")
        merger = self.getMerger(
            self.jobdir.src_root,
            self.merge_root,
            self.log)

        repos = {}
        for project in args['projects']:
            self.log.debug("Cloning %s/%s" % (project['connection'],
                                              project['name'],))
            repo = merger.getRepo(project['connection'],
                                  project['name'])
            repos[project['canonical_name']] = repo

        # The commit ID of the original item (before merging).  Used
        # later for line mapping.
        item_commit = None

        merge_items = [i for i in args['items'] if i.get('number')]
        if merge_items:
            # NOTE(tristanC): this is only valid for executor server context
            item_commit = self.doMergeChanges(merger, merge_items,
                                              args['repo_state'])
            if item_commit is None:
                # There was a merge conflict and we have already sent
                # a work complete result, don't run any jobs
                return False, merger

        state_items = [i for i in args['items'] if not i.get('number')]
        if state_items:
            merger.setRepoState(state_items, args['repo_state'])

        for project in args['projects']:
            repo = repos[project['canonical_name']]
            # If this project is the Zuul project and this is a ref
            # rather than a change, checkout the ref.
            if (project['canonical_name'] ==
                args['zuul']['project']['canonical_name'] and
                (not args['zuul'].get('branch')) and
                args['zuul'].get('ref')):
                ref = args['zuul']['ref']
            else:
                ref = None
            selected_ref, selected_desc = self.resolveBranch(
                project['canonical_name'],
                ref,
                args['branch'],
                args['override_branch'],
                args['override_checkout'],
                project['override_branch'],
                project['override_checkout'],
                project['default_branch'])
            self.log.info("Checking out %s %s %s",
                          project['canonical_name'], selected_desc,
                          selected_ref)
            repo.checkout(selected_ref)

            # Update the inventory variables to indicate the ref we
            # checked out
            p = args['zuul']['projects'][project['canonical_name']]
            p['checkout'] = selected_ref

        # Set the URL of the origin remote for each repo to a bogus
        # value. Keeping the remote allows tools to use it to determine
        # which commits are part of the current change.
        for repo in repos.values():
            repo.setRemoteUrl('file:///dev/null')

        return item_commit, merger

    def _blockPluginDirs(self, path):
        '''Prevent execution of playbooks or roles with plugins

        Plugins are loaded from roles and also if there is a plugin
        dir adjacent to the playbook.  Throw an error if the path
        contains a location that would cause a plugin to get loaded.

        '''
        for entry in os.listdir(path):
            entry = os.path.join(path, entry)
            if os.path.isdir(entry) and entry.endswith('_plugins'):
                raise ExecutorError(
                    "Ansible plugin dir %s found adjacent to playbook %s in "
                    "non-trusted repo." % (entry, path))

    def getAnsibleTimeout(self, start, timeout):
        if timeout is not None:
            now = time.time()
            elapsed = now - start
            timeout = timeout - elapsed
        return timeout

    def prepareKubeConfig(self, data):
        kube_cfg_path = os.path.join(self.jobdir.work_root, ".kube", "config")
        if os.path.exists(kube_cfg_path):
            kube_cfg = yaml.safe_load(open(kube_cfg_path))
        else:
            os.makedirs(os.path.dirname(kube_cfg_path), exist_ok=True)
            kube_cfg = {
                'apiVersion': 'v1',
                'kind': 'Config',
                'preferences': {},
                'users': [],
                'clusters': [],
                'contexts': [],
                'current-context': None,
            }
        # Add cluster
        cluster_name = urlsplit(data['host']).netloc.replace('.', '-')
        cluster = {
            'server': data['host'],
        }
        if data.get('ca_crt'):
            cluster['certificate-authority-data'] = data['ca_crt']
        if data['skiptls']:
            cluster['insecure-skip-tls-verify'] = True
        kube_cfg['clusters'].append({
            'name': cluster_name,
            'cluster': cluster,
        })

        # Add user
        user_name = "%s:%s" % (data['namespace'], data['user'])
        kube_cfg['users'].append({
            'name': user_name,
            'user': {
                'token': data['token'],
            },
        })

        # Add context
        data['context_name'] = "%s/%s" % (user_name, cluster_name)
        kube_cfg['contexts'].append({
            'name': data['context_name'],
            'context': {
                'user': user_name,
                'cluster': cluster_name,
                'namespace': data['namespace']
            }
        })
        if not kube_cfg['current-context']:
            kube_cfg['current-context'] = data['context_name']

        with open(kube_cfg_path, "w") as of:
            of.write(yaml.safe_dump(kube_cfg, default_flow_style=False))

    def prepareAnsibleFiles(self, args):
        all_vars = args['vars'].copy()
        check_varnames(all_vars)
        # TODO(mordred) Hack to work around running things with python3
        all_vars['ansible_python_interpreter'] = '/usr/bin/python2'
        all_vars['zuul'] = args['zuul'].copy()
        all_vars['zuul']['executor'] = dict(
            hostname=self.executor_server.hostname,
            src_root=self.jobdir.src_root,
            log_root=self.jobdir.log_root,
            work_root=self.jobdir.work_root,
            result_data_file=self.jobdir.result_data_file,
            inventory_file=self.jobdir.inventory)

        resources_nodes = []
        all_vars['zuul']['resources'] = {}
        for node in args['nodes']:
            if node.get('connection_type') in (
                    'namespace', 'project', 'kubectl'):
                # TODO: decrypt resource data using scheduler key
                data = node['connection_port']
                # Setup kube/config file
                self.prepareKubeConfig(data)
                # Convert connection_port in kubectl connection parameters
                node['connection_port'] = None
                node['kubectl_namespace'] = data['namespace']
                node['kubectl_context'] = data['context_name']
                # Add node information to zuul_resources
                all_vars['zuul']['resources'][node['name'][0]] = {
                    'namespace': data['namespace'],
                    'context': data['context_name'],
                }
                if node['connection_type'] in ('project', 'namespace'):
                    # Project are special nodes that are not the inventory
                    resources_nodes.append(node)
                else:
                    # Add the real pod name to the resources_var
                    all_vars['zuul']['resources'][
                        node['name'][0]]['pod'] = data['pod']
        # Remove resource node from nodes list
        for node in resources_nodes:
            args['nodes'].remove(node)

        nodes = self.getHostList(args)
        setup_inventory = make_setup_inventory_dict(nodes)
        inventory = make_inventory_dict(nodes, args, all_vars)

        with open(self.jobdir.setup_inventory, 'w') as setup_inventory_yaml:
            setup_inventory_yaml.write(
                yaml.safe_dump(setup_inventory, default_flow_style=False))

        print("Writting", self.jobdir.inventory)
        with open(self.jobdir.inventory, 'w') as inventory_yaml:
            inventory_yaml.write(
                yaml.safe_dump(inventory, default_flow_style=False))

        with open(self.jobdir.known_hosts, 'w') as known_hosts:
            for node in nodes:
                for key in node['host_keys']:
                    known_hosts.write('%s\n' % key)

        with open(self.jobdir.extra_vars, 'w') as extra_vars:
            extra_vars.write(
                yaml.safe_dump(args['extra_vars'], default_flow_style=False))

    def writeLoggingConfig(self):
        self.log.debug("Writing logging config for job %s %s",
                       self.jobdir.job_output_file,
                       self.jobdir.logging_json)
        logging_config = zuul.ansible.logconfig.JobLoggingConfig(
            job_output_file=self.jobdir.job_output_file)
        logging_config.writeJson(self.jobdir.logging_json)

    def getHostList(self, args):
        hosts = []
        for node in args['nodes']:
            # NOTE(mordred): This assumes that the nodepool launcher
            # and the zuul executor both have similar network
            # characteristics, as the launcher will do a test for ipv6
            # viability and if so, and if the node has an ipv6
            # address, it will be the interface_ip.  force-ipv4 can be
            # set to True in the clouds.yaml for a cloud if this
            # results in the wrong thing being in interface_ip
            # TODO(jeblair): Move this notice to the docs.
            for name in node['name']:
                ip = node.get('interface_ip')
                port = node.get('connection_port', node.get('ssh_port', 22))
                host_vars = args['host_vars'].get(name, {}).copy()
                check_varnames(host_vars)
                host_vars.update(dict(
                    ansible_host=ip,
                    ansible_user=self.executor_server.default_username,
                    ansible_port=port,
                    nodepool=dict(
                        label=node.get('label'),
                        az=node.get('az'),
                        cloud=node.get('cloud'),
                        provider=node.get('provider'),
                        region=node.get('region'),
                        host_id=node.get('host_id'),
                        interface_ip=node.get('interface_ip'),
                        public_ipv4=node.get('public_ipv4'),
                        private_ipv4=node.get('private_ipv4'),
                        public_ipv6=node.get('public_ipv6'))))

                username = node.get('username')
                if username:
                    host_vars['ansible_user'] = username

                connection_type = node.get('connection_type')
                if connection_type:
                    host_vars['ansible_connection'] = connection_type
                    if connection_type == "winrm":
                        host_vars['ansible_winrm_transport'] = 'certificate'
                        host_vars['ansible_winrm_cert_pem'] = \
                            self.winrm_pem_file
                        host_vars['ansible_winrm_cert_key_pem'] = \
                            self.winrm_key_file
                        # NOTE(tobiash): This is necessary when using default
                        # winrm self-signed certificates. This is probably what
                        # most installations want so hard code this here for
                        # now.
                        host_vars['ansible_winrm_server_cert_validation'] = \
                            'ignore'
                        if self.winrm_operation_timeout is not None:
                            host_vars['ansible_winrm_operation_timeout_sec'] =\
                                self.winrm_operation_timeout
                        if self.winrm_read_timeout is not None:
                            host_vars['ansible_winrm_read_timeout_sec'] = \
                                self.winrm_read_timeout

                host_keys = []
                for key in node.get('host_keys', []):
                    if port != 22:
                        host_keys.append("[%s]:%s %s" % (ip, port, key))
                    else:
                        host_keys.append("%s %s" % (ip, key))

                hosts.append(dict(
                    name=name,
                    host_vars=host_vars,
                    host_keys=host_keys))
        return hosts

    def _ansibleTimeout(self, msg):
        self.log.warning(msg)
        self.abortRunningProc()

    def runAnsible(self, cmd, timeout, playbook, wrapped=True):
        config_file = playbook.ansible_config
        env_copy = os.environ.copy()
        env_copy.update(self.ssh_agent.env)
        if ara_callbacks:
            env_copy['ARA_LOG_CONFIG'] = self.jobdir.logging_json
        env_copy['ZUUL_JOB_LOG_CONFIG'] = self.jobdir.logging_json
        env_copy['ZUUL_JOBDIR'] = self.jobdir.root
        env_copy['TMP'] = self.jobdir.local_tmp
        pythonpath = env_copy.get('PYTHONPATH')
        if pythonpath:
            pythonpath = [pythonpath]
        else:
            pythonpath = []
        if self.ansible_dir:
            pythonpath = [self.ansible_dir] + pythonpath
        env_copy['PYTHONPATH'] = os.path.pathsep.join(pythonpath)

        if playbook.trusted:
            opt_prefix = 'trusted'
        else:
            opt_prefix = 'untrusted'
        ro_paths = get_default(self.executor_server.config, 'executor',
                               '%s_ro_paths' % opt_prefix)
        rw_paths = get_default(self.executor_server.config, 'executor',
                               '%s_rw_paths' % opt_prefix)
        ro_paths = ro_paths.split(":") if ro_paths else []
        rw_paths = rw_paths.split(":") if rw_paths else []

        if self.executor_server.ansible_dir:
            ro_paths.append(self.executor_server.ansible_dir)
        ro_paths.append(self.jobdir.ansible_root)
        ro_paths.append(self.jobdir.trusted_root)
        ro_paths.append(self.jobdir.untrusted_root)
        ro_paths.append(playbook.root)

        rw_paths.append(self.jobdir.ansible_cache_root)

        if self.executor_variables_file:
            ro_paths.append(self.executor_variables_file)

        secrets = {}
        if playbook.secrets_content:
            secrets[playbook.secrets] = playbook.secrets_content

        if wrapped:
            wrapper = self.executor_server.execution_wrapper
        else:
            wrapper = self.connections.drivers['nullwrap']

        context = wrapper.getExecutionContext(ro_paths, rw_paths, secrets)

        popen = context.getPopen(
            work_dir=self.jobdir.work_root,
            ssh_auth_sock=env_copy.get('SSH_AUTH_SOCK'))

        env_copy['ANSIBLE_CONFIG'] = config_file
        # NOTE(pabelanger): Default HOME variable to jobdir.work_root, as it is
        # possible we don't bind mount current zuul user home directory.
        env_copy['HOME'] = self.jobdir.work_root

        with self.proc_lock:
            if self.aborted:
                return (self.RESULT_ABORTED, None)
            self.log.debug("Ansible command: ANSIBLE_CONFIG=%s %s",
                           config_file, " ".join(shlex.quote(c) for c in cmd))
            self.proc = popen(
                cmd,
                cwd=self.jobdir.work_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                env=env_copy,
            )

        syntax_buffer = []
        ret = None
        if timeout:
            watchdog = Watchdog(timeout, self._ansibleTimeout,
                                ("Ansible timeout exceeded",))
            watchdog.start()
        try:
            # Use manual idx instead of enumerate so that RESULT lines
            # don't count towards BUFFER_LINES_FOR_SYNTAX
            idx = 0
            for line in iter(self.proc.stdout.readline, b''):
                if line.startswith(b'RESULT'):
                    # TODO(mordred) Process result commands if sent
                    continue
                else:
                    idx += 1
                if idx < BUFFER_LINES_FOR_SYNTAX:
                    syntax_buffer.append(line)
                line = line[:1024].rstrip()
                self.log.debug("Ansible output: %s" % (line,))
            self.log.debug("Ansible output terminated")
            cpu_times = self.proc.cpu_times()
            self.log.debug("Ansible cpu times: user=%.2f, system=%.2f, "
                           "children_user=%.2f, "
                           "children_system=%.2f" %
                           (cpu_times.user, cpu_times.system,
                            cpu_times.children_user,
                            cpu_times.children_system))
            self.cpu_times['user'] += cpu_times.user
            self.cpu_times['system'] += cpu_times.system
            self.cpu_times['children_user'] += cpu_times.children_user
            self.cpu_times['children_system'] += cpu_times.children_system
            ret = self.proc.wait()
            self.log.debug("Ansible exit code: %s" % (ret,))
        finally:
            if timeout:
                watchdog.stop()
                self.log.debug("Stopped watchdog")
            self.log.debug("Stopped disk job killer")

        with self.proc_lock:
            self.proc = None

        if timeout and watchdog.timed_out:
            return (self.RESULT_TIMED_OUT, None)
        # Note: Unlike documented ansible currently wrongly returns 4 on
        # unreachable so we have the zuul_unreachable callback module that
        # creates the file job-output.unreachable in case there were
        # unreachable nodes. This can be removed once ansible returns a
        # distinct value for unreachable.
        if ret == 3 or os.path.exists(self.jobdir.job_unreachable_file):
            # AnsibleHostUnreachable: We had a network issue connecting to
            # our zuul-worker.
            return (self.RESULT_UNREACHABLE, None)
        elif ret == -9:
            # Received abort request.
            return (self.RESULT_ABORTED, None)
        elif ret == 1:
            with open(self.jobdir.job_output_file, 'a') as job_output:
                found_marker = False
                for line in syntax_buffer:
                    if line.startswith(b'ERROR!'):
                        found_marker = True
                    if not found_marker:
                        continue
                    job_output.write("{now} | {line}\n".format(
                        now=datetime.datetime.now(),
                        line=line.decode('utf-8').rstrip()))
        elif ret == 4:
            # Ansible could not parse the yaml.
            self.log.debug("Ansible parse error")
            # TODO(mordred) If/when we rework use of logger in ansible-playbook
            # we'll want to change how this works to use that as well. For now,
            # this is what we need to do.
            # TODO(mordred) We probably want to put this into the json output
            # as well.
            with open(self.jobdir.job_output_file, 'a') as job_output:
                job_output.write("{now} | ANSIBLE PARSE ERROR\n".format(
                    now=datetime.datetime.now()))
                for line in syntax_buffer:
                    job_output.write("{now} | {line}\n".format(
                        now=datetime.datetime.now(),
                        line=line.decode('utf-8').rstrip()))
        elif ret == 250:
            # Unexpected error from ansible
            with open(self.jobdir.job_output_file, 'a') as job_output:
                job_output.write("{now} | UNEXPECTED ANSIBLE ERROR\n".format(
                    now=datetime.datetime.now()))
                found_marker = False
                for line in syntax_buffer:
                    if line.startswith(b'ERROR! Unexpected Exception'):
                        found_marker = True
                    if not found_marker:
                        continue
                    job_output.write("{now} | {line}\n".format(
                        now=datetime.datetime.now(),
                        line=line.decode('utf-8').rstrip()))

        return (self.RESULT_NORMAL, ret)

    def runPlaybooks(self, args):
        result = None

        # Run the Ansible 'setup' module on all hosts in the inventory
        # at the start of the job with a 60 second timeout.  If we
        # aren't able to connect to all the hosts and gather facts
        # within that timeout, there is likely a network problem
        # between here and the hosts in the inventory; return them and
        # reschedule the job.
        setup_status, setup_code = self.runAnsibleSetup(
            self.jobdir.setup_playbook)
        if setup_status != self.RESULT_NORMAL or setup_code != 0:
            return result

        pre_failed = False
        success = False
        if self.executor_server.statsd:
            key = "zuul.executor.{hostname}.starting_builds"
            self.executor_server.statsd.timing(
                key, (time.monotonic() - self.time_starting_build) * 1000)

        self.started = True
        time_started = time.time()
        # timeout value is "total" job timeout which accounts for
        # pre-run and run playbooks. post-run is different because
        # it is used to copy out job logs and we want to do our best
        # to copy logs even when the job has timed out.
        job_timeout = args['timeout']
        for index, playbook in enumerate(self.jobdir.pre_playbooks):
            # TODOv3(pabelanger): Implement pre-run timeout setting.
            ansible_timeout = self.getAnsibleTimeout(time_started, job_timeout)
            pre_status, pre_code = self.runAnsiblePlaybook(
                playbook, ansible_timeout, phase='pre', index=index)
            if pre_status != self.RESULT_NORMAL or pre_code != 0:
                # These should really never fail, so return None and have
                # zuul try again
                pre_failed = True
                break

        self.log.debug(
            "Overall ansible cpu times: user=%.2f, system=%.2f, "
            "children_user=%.2f, children_system=%.2f" %
            (self.cpu_times['user'], self.cpu_times['system'],
             self.cpu_times['children_user'],
             self.cpu_times['children_system']))

        if not pre_failed:
            ansible_timeout = self.getAnsibleTimeout(time_started, job_timeout)
            job_status, job_code = self.runAnsiblePlaybook(
                self.jobdir.playbook, ansible_timeout, phase='run')
            if job_status == self.RESULT_ABORTED:
                return 'ABORTED'
            elif job_status == self.RESULT_TIMED_OUT:
                # Set the pre-failure flag so this doesn't get
                # overridden by a post-failure.
                pre_failed = True
                result = 'TIMED_OUT'
            elif job_status == self.RESULT_NORMAL:
                success = (job_code == 0)
                if success:
                    result = 'SUCCESS'
                else:
                    result = 'FAILURE'
            else:
                # The result of the job is indeterminate.  Zuul will
                # run it again.
                return None

        # check if we need to pause here
        result_data = self.getResultData()
        pause = result_data.get('zuul', {}).get('pause')
        if pause:
            self.pause()

        post_timeout = args['post_timeout']
        unreachable = False
        for index, playbook in enumerate(self.jobdir.post_playbooks):
            # Post timeout operates a little differently to the main job
            # timeout. We give each post playbook the full post timeout to
            # do its job because post is where you'll often record job logs
            # which are vital to understanding why timeouts have happened in
            # the first place.
            post_status, post_code = self.runAnsiblePlaybook(
                playbook, post_timeout, success, phase='post', index=index)
            if post_status == self.RESULT_ABORTED:
                return 'ABORTED'
            if post_status == self.RESULT_UNREACHABLE:
                # In case we encounter unreachable nodes we need to return None
                # so the job can be retried. However in the case of post
                # playbooks we should still try to run all playbooks to get a
                # chance to upload logs.
                unreachable = True
            if post_status != self.RESULT_NORMAL or post_code != 0:
                success = False
                # If we encountered a pre-failure, that takes
                # precedence over the post result.
                if not pre_failed:
                    result = 'POST_FAILURE'
                if (index + 1) == len(self.jobdir.post_playbooks):
                    self._logFinalPlaybookError()

        if unreachable:
            return None

        return result

    def runAnsibleSetup(self, playbook):
        if self.executor_server.verbose:
            verbose = '-vvv'
        else:
            verbose = '-v'

        cmd = ['ansible', '*', verbose, '-m', 'setup',
               '-i', self.jobdir.setup_inventory,
               '-a', 'gather_subset=!all']
        if self.executor_variables_file is not None:
            cmd.extend(['-e@%s' % self.executor_variables_file])

        result, code = self.runAnsible(
            cmd=cmd, timeout=60, playbook=playbook,
            wrapped=False)
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.executor_server.statsd:
            base_key = "zuul.executor.{hostname}.phase.setup"
            self.executor_server.statsd.incr(base_key + ".%s" %
                                             self.RESULT_MAP[result])
        return result, code

    def runAnsibleCleanup(self, playbook):
        # TODO(jeblair): This requires a bugfix in Ansible 2.4
        # Once this is used, increase the controlpersist timeout.
        return (self.RESULT_NORMAL, 0)

        if self.executor_server.verbose:
            verbose = '-vvv'
        else:
            verbose = '-v'

        cmd = ['ansible', '*', verbose, '-m', 'meta',
               '-a', 'reset_connection']

        result, code = self.runAnsible(
            cmd=cmd, timeout=60, playbook=playbook,
            wrapped=False)
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.executor_server.statsd:
            base_key = "zuul.executor.{hostname}.phase.cleanup"
            self.executor_server.statsd.incr(base_key + ".%s" %
                                             self.RESULT_MAP[result])
        return result, code

    def emitPlaybookBanner(self, playbook, step, phase, result=None):
        # This is used to print a header and a footer, respectively at the
        # beginning and the end of each playbook execution.
        # We are doing it from the executor rather than from a callback because
        # the parameters are not made available to the callback until it's too
        # late.
        phase = phase or ''
        trusted = playbook.trusted
        trusted = 'trusted' if trusted else 'untrusted'
        branch = playbook.branch
        playbook = playbook.canonical_name_and_path

        if phase and phase != 'run':
            phase = '{phase}-run'.format(phase=phase)
        phase = phase.upper()

        if result is not None:
            result = self.RESULT_MAP[result]
            msg = "{phase} {step} {result}: [{trusted} : {playbook}@{branch}]"
            msg = msg.format(phase=phase, step=step, result=result,
                             trusted=trusted, playbook=playbook, branch=branch)
        else:
            msg = "{phase} {step}: [{trusted} : {playbook}@{branch}]"
            msg = msg.format(phase=phase, step=step, trusted=trusted,
                             playbook=playbook, branch=branch)

        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write("{now} | {msg}\n".format(
                now=datetime.datetime.now(),
                msg=msg))

    def runAnsiblePlaybook(self, playbook, timeout, success=None,
                           phase=None, index=None):
        if self.executor_server.verbose:
            verbose = '-vvv'
        else:
            verbose = '-v'

        cmd = ['ansible-playbook', verbose, playbook.path]
        if playbook.secrets_content:
            cmd.extend(['-e', '@' + playbook.secrets])

        cmd.extend(['-e', '@' + self.jobdir.extra_vars])

        if success is not None:
            cmd.extend(['-e', 'zuul_success=%s' % str(bool(success))])

        if phase:
            cmd.extend(['-e', 'zuul_execution_phase=%s' % phase])

        if index is not None:
            cmd.extend(['-e', 'zuul_execution_phase_index=%s' % index])

        cmd.extend(['-e', 'zuul_execution_trusted=%s' % str(playbook.trusted)])
        cmd.extend([
            '-e',
            'zuul_execution_canonical_name_and_path=%s'
            % playbook.canonical_name_and_path])
        cmd.extend(['-e', 'zuul_execution_branch=%s' % str(playbook.branch)])

        if self.executor_variables_file is not None:
            cmd.extend(['-e@%s' % self.executor_variables_file])

        self.emitPlaybookBanner(playbook, 'START', phase)

        result, code = self.runAnsible(
            cmd=cmd, timeout=timeout, playbook=playbook)
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.executor_server.statsd:
            base_key = "zuul.executor.{hostname}.phase.{phase}"
            self.executor_server.statsd.incr(
                base_key + ".{result}",
                result=self.RESULT_MAP[result],
                phase=phase or 'unknown')

        self.emitPlaybookBanner(playbook, 'END', phase, result=result)
        return result, code

    def getResultData(self):
        data = {}
        try:
            with open(self.jobdir.result_data_file) as f:
                file_data = f.read()
                if file_data:
                    data = json.loads(file_data)
        except Exception:
            self.log.exception("Unable to load result data:")
        return data

    def _logFinalPlaybookError(self):
        # Failures in the final post playbook can include failures
        # uploading logs, which makes diagnosing issues difficult.
        # Grab the output from the last playbook from the json
        # file and log it.
        json_output = self.jobdir.job_output_file.replace('txt', 'json')
        self.log.debug("Final playbook failed")
        if not os.path.exists(json_output):
            self.log.debug("JSON logfile {logfile} is missing".format(
                logfile=json_output))
            return
        try:
            output = json.load(open(json_output, 'r'))
            last_playbook = output[-1]
            # Transform json to yaml - because it's easier to read and given
            # the size of the data it'll be extra-hard to read this as an
            # all on one line stringified nested dict.
            yaml_out = yaml.safe_dump(last_playbook, default_flow_style=False)
            for line in yaml_out.split('\n'):
                self.log.debug(line)
        except Exception:
            self.log.exception(
                "Could not decode json from {logfile}".format(
                    logfile=json_output))


class AnsibleJob(AnsibleJobBase):
    "This class executes and performs the full Ansible Job"

    def __init__(self, executor_server, job):
        super(AnsibleJob, self).__init__(
            executor_server, json.loads(job.arguments))
        logger = logging.getLogger("zuul.AnsibleJob")
        self.log = AnsibleJobLogAdapter(logger, {'job': job.unique})
        self.job = job
        self.proc = None
        self.running = False
        self.started = False  # Whether playbooks have started running
        self.time_starting_build = None
        self.paused = False
        self.aborted_reason = None
        self._resume_event = threading.Event()
        self.thread = None
        self.private_key_file = get_default(self.executor_server.config,
                                            'executor', 'private_key_file',
                                            '~/.ssh/id_rsa')
        self.winrm_key_file = get_default(self.executor_server.config,
                                          'executor', 'winrm_cert_key_file',
                                          '~/.winrm/winrm_client_cert.key')
        self.winrm_pem_file = get_default(self.executor_server.config,
                                          'executor', 'winrm_cert_pem_file',
                                          '~/.winrm/winrm_client_cert.pem')
        self.winrm_operation_timeout = get_default(
            self.executor_server.config,
            'executor',
            'winrm_operation_timeout_sec')
        self.winrm_read_timeout = get_default(
            self.executor_server.config,
            'executor',
            'winrm_read_timeout_sec')
        self.ssh_agent = SshAgent()

        if self.executor_server.config.has_option('executor', 'variables'):
            self.executor_variables_file = self.executor_server.config.get(
                'executor', 'variables')

    def getMerger(self, root, cache_root=None, logger=None):
        return self.executor_server._getMerger(root, cache_root, logger)

    def run(self):
        self.running = True
        self.thread = threading.Thread(target=self.execute,
                                       name='build-%s' % self.job.unique)
        self.thread.start()

    def stop(self, reason=None):
        self.aborted = True
        self.aborted_reason = reason

        # if paused we need to resume the job so it can be stopped
        self.resume()
        self.abortRunningProc()

    def pause(self):
        self.log.info(
            "Pausing job %s for ref %s (change %s)" % (
                self.arguments['zuul']['job'],
                self.arguments['zuul']['ref'],
                self.arguments['zuul']['change_url']))
        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write(
                "{now} |\n"
                "{now} | Job paused\n".format(now=datetime.datetime.now()))

        self.paused = True

        data = {'paused': self.paused, 'data': self.getResultData()}
        self.job.sendWorkData(json.dumps(data))
        self._resume_event.wait()

    def resume(self):
        if not self.paused:
            return

        self.log.info(
            "Resuming job %s for ref %s (change %s)" % (
                self.arguments['zuul']['job'],
                self.arguments['zuul']['ref'],
                self.arguments['zuul']['change_url']))
        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write(
                "{now} | Job resumed\n"
                "{now} |\n".format(now=datetime.datetime.now()))

        self.paused = False
        self._resume_event.set()

    def wait(self):
        if self.thread:
            self.thread.join()

    def execute(self):
        try:
            self.time_starting_build = time.monotonic()
            self.ssh_agent.start()
            self.ssh_agent.add(self.private_key_file)
            for key in self.arguments.get('ssh_keys', []):
                self.ssh_agent.addData(key['name'], key['key'])
            self.jobdir = JobDir(self.executor_server.jobdir_root,
                                 self.executor_server.keep_jobdir,
                                 str(self.job.unique))
            self._execute()
        except ExecutorError as e:
            result_data = json.dumps(dict(result='ERROR',
                                          error_detail=e.args[0]))
            self.log.debug("Sending result: %s" % (result_data,))
            self.job.sendWorkComplete(result_data)
        except Exception:
            self.log.exception("Exception while executing job")
            self.job.sendWorkException(traceback.format_exc())
        finally:
            self.running = False
            if self.jobdir:
                try:
                    self.jobdir.cleanup()
                except Exception:
                    self.log.exception("Error cleaning up jobdir:")
            if self.ssh_agent:
                try:
                    self.ssh_agent.stop()
                except Exception:
                    self.log.exception("Error stopping SSH agent:")
            try:
                self.executor_server.finishJob(self.job.unique)
            except Exception:
                self.log.exception("Error finalizing job thread:")

    def _execute(self):
        args = self.arguments
        self.log.info(
            "Beginning job %s for ref %s (change %s)" % (
                args['zuul']['job'],
                args['zuul']['ref'],
                args['zuul']['change_url']))
        self.log.debug("Job root: %s" % (self.jobdir.root,))

        item_commit, merger = self.prepareRepositories(
            self.executor_server.update)
        if item_commit is False:
            # There was a merge conflict and we have already sent
            # a work complete result, don't run any jobs
            return

        # This prepares each playbook and the roles needed for each.
        self.preparePlaybooks(args)

        self.prepareAnsibleFiles(args)
        self.writeLoggingConfig()

        data = {
            # TODO(mordred) worker_name is needed as a unique name for the
            # client to use for cancelling jobs on an executor. It's defaulting
            # to the hostname for now, but in the future we should allow
            # setting a per-executor override so that one can run more than
            # one executor on a host.
            'worker_name': self.executor_server.hostname,
            'worker_hostname': self.executor_server.hostname,
            'worker_log_port': self.executor_server.log_streaming_port
        }
        if self.executor_server.log_streaming_port != DEFAULT_FINGER_PORT:
            data['url'] = "finger://{hostname}:{port}/{uuid}".format(
                hostname=data['worker_hostname'],
                port=data['worker_log_port'],
                uuid=self.job.unique)
        else:
            data['url'] = 'finger://{hostname}/{uuid}'.format(
                hostname=data['worker_hostname'],
                uuid=self.job.unique)

        self.job.sendWorkData(json.dumps(data))
        self.job.sendWorkStatus(0, 100)

        result = self.runPlaybooks(args)

        # Stop the persistent SSH connections.
        setup_status, setup_code = self.runAnsibleCleanup(
            self.jobdir.setup_playbook)

        if self.aborted_reason == self.RESULT_DISK_FULL:
            result = 'DISK_FULL'
        data = self.getResultData()
        warnings = []
        self.mapLines(merger, args, data, item_commit, warnings)
        result_data = json.dumps(dict(result=result,
                                      warnings=warnings,
                                      data=data))
        self.log.debug("Sending result: %s" % (result_data,))
        self.job.sendWorkComplete(result_data)

    def mapLines(self, merger, args, data, commit, warnings):
        # The data and warnings arguments are mutated in this method.

        # If we received file comments, map the line numbers before
        # we send the result.
        fc = data.get('zuul', {}).get('file_comments')
        if not fc:
            return
        disable = data.get('zuul', {}).get('disable_file_comment_line_mapping')
        if disable:
            return

        try:
            filecomments.validate(fc)
        except Exception as e:
            warnings.append("Job %s: validation error in file comments: %s" %
                            (args['zuul']['job'], str(e)))
            del data['zuul']['file_comments']
            return

        repo = None
        for project in args['projects']:
            if (project['canonical_name'] !=
                args['zuul']['project']['canonical_name']):
                continue
            repo = merger.getRepo(project['connection'],
                                  project['name'])
        # If the repo doesn't exist, abort
        if not repo:
            return

        # Check out the selected ref again in case the job altered the
        # repo state.
        p = args['zuul']['projects'][project['canonical_name']]
        selected_ref = p['checkout']

        self.log.info("Checking out %s %s for line mapping",
                      project['canonical_name'], selected_ref)
        try:
            repo.checkout(selected_ref)
        except Exception:
            # If checkout fails, abort
            self.log.exception("Error checking out repo for line mapping")
            warnings.append("Job %s: unable to check out repo "
                            "for file comments" % (args['zuul']['job']))
            return

        lines = filecomments.extractLines(fc)

        new_lines = {}
        for (filename, lineno) in lines:
            try:
                new_lineno = repo.mapLine(commit, filename, lineno)
            except Exception as e:
                # Log at debug level since it's likely a job issue
                self.log.debug("Error mapping line:", exc_info=True)
                if isinstance(e, git.GitCommandError):
                    msg = e.stderr
                else:
                    msg = str(e)
                warnings.append("Job %s: unable to map line "
                                "for file comments: %s" %
                                (args['zuul']['job'], msg))
                new_lineno = None
            if new_lineno is not None:
                new_lines[(filename, lineno)] = new_lineno

        filecomments.updateLines(fc, new_lines)

    def doMergeChanges(self, merger, items, repo_state):
        try:
            ret = merger.mergeChanges(items, repo_state=repo_state)
        except ValueError:
            # Return ABORTED so that we'll try again. At this point all of
            # the refs we're trying to merge should be valid refs. If we
            # can't fetch them, it should resolve itself.
            self.log.exception("Could not fetch refs to merge from remote")
            result = dict(result='ABORTED')
            self.job.sendWorkComplete(json.dumps(result))
            return None
        if not ret:  # merge conflict
            result = dict(result='MERGER_FAILURE')
            if self.executor_server.statsd:
                base_key = "zuul.executor.{hostname}.merger"
                self.executor_server.statsd.incr(base_key + ".FAILURE")
            self.job.sendWorkComplete(json.dumps(result))
            return None

        if self.executor_server.statsd:
            base_key = "zuul.executor.{hostname}.merger"
            self.executor_server.statsd.incr(base_key + ".SUCCESS")
        recent = ret[3]
        orig_commit = ret[4]
        for key, commit in recent.items():
            (connection, project, branch) = key
            repo = merger.getRepo(connection, project)
            repo.setRef('refs/heads/' + branch, commit)
        return orig_commit

    def writeAnsibleConfig(self, jobdir_playbook):
        trusted = jobdir_playbook.trusted

        # TODO(mordred) This should likely be extracted into a more generalized
        #               mechanism for deployers being able to add callback
        #               plugins.
        if ara_callbacks:
            callback_path = '%s:%s' % (
                self.executor_server.callback_dir,
                os.path.dirname(ara_callbacks.__file__))
        else:
            callback_path = self.executor_server.callback_dir
        with open(jobdir_playbook.ansible_config, 'w') as config:
            config.write('[defaults]\n')
            config.write('inventory = %s\n' % self.jobdir.inventory)
            config.write('local_tmp = %s\n' % self.jobdir.local_tmp)
            config.write('retry_files_enabled = False\n')
            config.write('gathering = smart\n')
            config.write('fact_caching = jsonfile\n')
            config.write('fact_caching_connection = %s\n' %
                         self.jobdir.fact_cache)
            config.write('library = %s\n'
                         % self.executor_server.library_dir)
            config.write('command_warnings = False\n')
            config.write('callback_plugins = %s\n' % callback_path)
            config.write('stdout_callback = zuul_stream\n')
            config.write('filter_plugins = %s\n'
                         % self.executor_server.filter_dir)
            # bump the timeout because busy nodes may take more than
            # 10s to respond
            config.write('timeout = 30\n')

            # We need at least the general action dir as this overwrites the
            # command action plugin for log streaming.
            action_dirs = [self.executor_server.action_dir_general]
            if not trusted:
                action_dirs.append(self.executor_server.action_dir)
                config.write('lookup_plugins = %s\n'
                             % self.executor_server.lookup_dir)

            config.write('action_plugins = %s\n'
                         % ':'.join(action_dirs))

            if jobdir_playbook.roles_path:
                config.write('roles_path = %s\n' % ':'.join(
                    jobdir_playbook.roles_path))

            # On playbooks with secrets we want to prevent the
            # printing of args since they may be passed to a task or a
            # role. Otherwise, printing the args could be useful for
            # debugging.
            config.write('display_args_to_stdout = %s\n' %
                         str(not jobdir_playbook.secrets_content))

            # Increase the internal poll interval of ansible.
            # The default interval of 0.001s is optimized for interactive
            # ui at the expense of CPU load. As we have a non-interactive
            # automation use case a longer poll interval is more suitable
            # and reduces CPU load of the ansible process.
            config.write('internal_poll_interval = 0.01\n')

            config.write('[ssh_connection]\n')
            # NOTE(pabelanger): Try up to 3 times to run a task on a host, this
            # helps to mitigate UNREACHABLE host errors with SSH.
            config.write('retries = 3\n')
            # NB: when setting pipelining = True, keep_remote_files
            # must be False (the default).  Otherwise it apparently
            # will override the pipelining option and effectively
            # disable it.  Pipelining has a side effect of running the
            # command without a tty (ie, without the -tt argument to
            # ssh).  We require this behavior so that if a job runs a
            # command which expects interactive input on a tty (such
            # as sudo) it does not hang.
            config.write('pipelining = True\n')
            config.write('control_path_dir = %s\n' % self.jobdir.control_path)
            ssh_args = "-o ControlMaster=auto -o ControlPersist=60s " \
                "-o ServerAliveInterval=60 " \
                "-o UserKnownHostsFile=%s" % self.jobdir.known_hosts
            config.write('ssh_args = %s\n' % ssh_args)

    def abortRunningProc(self):
        with self.proc_lock:
            if not self.proc:
                self.log.debug("Abort: no process is running")
                return
            self.log.debug("Abort: sending kill signal to job "
                           "process group")
            try:
                pgid = os.getpgid(self.proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                self.log.exception("Exception while killing ansible process:")


def construct_gearman_params(uuid, sched, job, item, pipeline,
                             dependent_changes=[], merger_items=[],
                             redact_secrets_and_keys=True):

    tenant = pipeline.tenant
    project = dict(
        name=item.change.project.name,
        short_name=item.change.project.name.split('/')[-1],
        canonical_hostname=item.change.project.canonical_hostname,
        canonical_name=item.change.project.canonical_name,
        src_dir=os.path.join('src', item.change.project.canonical_name),
    )

    zuul_params = dict(build=uuid,
                       buildset=item.current_build_set.uuid,
                       ref=item.change.ref,
                       pipeline=pipeline.name,
                       job=job.name,
                       voting=job.voting,
                       project=project,
                       tenant=tenant.name,
                       timeout=job.timeout,
                       jobtags=sorted(job.tags),
                       _inheritance_path=list(job.inheritance_path))
    if job.override_checkout:
        zuul_params['override_checkout'] = job.override_checkout
    if hasattr(item.change, 'branch'):
        zuul_params['branch'] = item.change.branch
    if hasattr(item.change, 'tag'):
        zuul_params['tag'] = item.change.tag
    if hasattr(item.change, 'number'):
        zuul_params['change'] = str(item.change.number)
    if hasattr(item.change, 'url'):
        zuul_params['change_url'] = item.change.url
    if hasattr(item.change, 'patchset'):
        zuul_params['patchset'] = str(item.change.patchset)
    if (hasattr(item.change, 'oldrev') and item.change.oldrev
        and item.change.oldrev != '0' * 40):
        zuul_params['oldrev'] = item.change.oldrev
    if (hasattr(item.change, 'newrev') and item.change.newrev
        and item.change.newrev != '0' * 40):
        zuul_params['newrev'] = item.change.newrev
    zuul_params['projects'] = {}  # Set below
    zuul_params['items'] = dependent_changes
    zuul_params['child_jobs'] = list(item.job_graph.getDirectDependentJobs(
        job.name))

    params = dict()
    params['job'] = job.name
    params['timeout'] = job.timeout
    params['post_timeout'] = job.post_timeout
    params['items'] = merger_items
    params['projects'] = []
    if hasattr(item.change, 'branch'):
        params['branch'] = item.change.branch
    else:
        params['branch'] = None
    params['override_branch'] = job.override_branch
    params['override_checkout'] = job.override_checkout
    params['repo_state'] = item.current_build_set.repo_state

    def make_playbook(playbook):
        d = playbook.toDict(redact_secrets=redact_secrets_and_keys)
        for role in d['roles']:
            if role['type'] != 'zuul':
                continue
            project_metadata = item.layout.getProjectMetadata(
                role['project_canonical_name'])
            if project_metadata:
                role['project_default_branch'] = \
                    project_metadata.default_branch
            else:
                role['project_default_branch'] = 'master'
            role_trusted, role_project = item.layout.tenant.getProject(
                role['project_canonical_name'])
            role_connection = role_project.source.connection
            role['connection'] = role_connection.connection_name
            role['project'] = role_project.name
        return d

    if job.name != 'noop':
        params['playbooks'] = [make_playbook(x) for x in job.run]
        params['pre_playbooks'] = [make_playbook(x) for x in job.pre_run]
        params['post_playbooks'] = [make_playbook(x) for x in job.post_run]

    params['ssh_keys'] = []
    if pipeline.post_review:
        if redact_secrets_and_keys:
            ssh_key = "REDACTED"
        else:
            ssh_key = item.change.project.private_ssh_key
        params['ssh_keys'].append(dict(
            name='%s project key' % item.change.project.canonical_name,
            key=ssh_key))
    params['vars'] = job.variables
    params['extra_vars'] = job.extra_variables
    params['host_vars'] = job.host_variables
    params['group_vars'] = job.group_variables
    params['zuul'] = zuul_params
    projects = set()
    required_projects = set()

    def make_project_dict(project, override_branch=None,
                          override_checkout=None):
        project_metadata = item.layout.getProjectMetadata(
            project.canonical_name)
        if project_metadata:
            project_default_branch = project_metadata.default_branch
        else:
            project_default_branch = 'master'
        connection = project.source.connection
        return dict(connection=connection.connection_name,
                    name=project.name,
                    canonical_name=project.canonical_name,
                    override_branch=override_branch,
                    override_checkout=override_checkout,
                    default_branch=project_default_branch)

    if job.required_projects:
        for job_project in job.required_projects.values():
            (trusted, project) = tenant.getProject(
                job_project.project_name)
            if project is None:
                raise Exception("Unknown project %s" %
                                (job_project.project_name,))
            params['projects'].append(
                make_project_dict(project,
                                  job_project.override_branch,
                                  job_project.override_checkout))
            projects.add(project)
            required_projects.add(project)
    for change in dependent_changes:
        # We have to find the project this way because it may not
        # be registered in the tenant (ie, a foreign project).
        source = sched.connections.getSourceByCanonicalHostname(
            change['project']['canonical_hostname'])
        project = source.getProject(change['project']['name'])
        if project not in projects:
            params['projects'].append(make_project_dict(project))
            projects.add(project)
    for p in projects:
        zuul_params['projects'][p.canonical_name] = (dict(
            name=p.name,
            short_name=p.name.split('/')[-1],
            # Duplicate this into the dict too, so that iterating
            # project.values() is easier for callers
            canonical_name=p.canonical_name,
            canonical_hostname=p.canonical_hostname,
            src_dir=os.path.join('src', p.canonical_name),
            required=(p in required_projects),
        ))

    return params
