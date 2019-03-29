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

import abc
import base64
import collections
import copy
import datetime
import json
import logging
import os
import psutil
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

import zuul.ansible.logconfig
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.yamlutil import yaml


BUFFER_LINES_FOR_SYNTAX = 200
DEFAULT_FINGER_PORT = 7900
DEFAULT_STREAM_PORT = 19885
BLACKLISTED_ANSIBLE_CONNECTION_TYPES = [
    'network_cli', 'kubectl', 'project', 'namespace']
BLACKLISTED_VARS = dict(
    ansible_ssh_executable='ssh',
    ansible_ssh_common_args='-o PermitLocalCommand=no',
    ansible_sftp_extra_args='-o PermitLocalCommand=no',
    ansible_scp_extra_args='-o PermitLocalCommand=no',
    ansible_ssh_extra_args='-o PermitLocalCommand=no',
)


class ExecutorError(Exception):
    """A non-transient run-time executor error

    This class represents error conditions detected by the executor
    when preparing to run a job which we know are consistently fatal.
    Zuul should not reschedule the build in these cases.
    """
    pass


class RoleNotFoundError(ExecutorError):
    pass


class PluginFoundError(ExecutorError):
    pass


class MergerFetchFailure(Exception):
    """ Raised when failing to fetch all the required refs """
    pass


class MergerMergeFailure(Exception):
    """ A ref failed to merge """
    pass


class Watchdog(object):
    def __init__(self, timeout, function, args):
        self.timeout = timeout
        self.function = function
        self.args = args
        self.thread = threading.Thread(target=self._run,
                                       name='watchdog')
        self.thread.daemon = True
        self.timed_out = None

        self.end = 0

        self._running = False
        self._stop_event = threading.Event()

    def _run(self):
        while self._running and time.time() < self.end:
            self._stop_event.wait(10)
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
        self._stop_event.set()


class SshAgent(object):

    def __init__(self, zuul_event_id=None, build=None):
        self.env = {}
        self.ssh_agent = None
        self.log = get_annotated_logger(
            logging.getLogger("zuul.ExecutorServer"),
            zuul_event_id, build=build)

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

    def __del__(self):
        try:
            self.stop()
        except Exception:
            self.log.exception('Exception in SshAgent destructor')
        try:
            super().__del__(self)
        except AttributeError:
            pass

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


class KubeFwd(object):
    kubectl_command = 'kubectl'

    def __init__(self, zuul_event_id, build, kubeconfig, context,
                 namespace, pod):
        self.port = None
        self.fwd = None
        self.log = get_annotated_logger(
            logging.getLogger("zuul.ExecutorServer"),
            zuul_event_id, build=build)
        self.kubeconfig = kubeconfig
        self.context = context
        self.namespace = namespace
        self.pod = pod

    def start(self):
        if self.fwd:
            return
        with open('/dev/null', 'r+') as devnull:
            fwd = subprocess.Popen(
                [self.kubectl_command, '--kubeconfig=%s' % self.kubeconfig,
                 '--context=%s' % self.context,
                 '-n', self.namespace,
                 'port-forward',
                 'pod/%s' % self.pod, ':19885'],
                close_fds=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=devnull)
        line = fwd.stdout.readline().decode('utf8')
        m = re.match(r'^Forwarding from 127.0.0.1:(\d+) -> 19885', line)
        if m:
            self.port = m.group(1)
        else:
            try:
                self.log.error("Could not find the forwarded port: %s", line)
                fwd.kill()
            except Exception:
                pass
            raise Exception("Unable to start kubectl port forward")
        self.fwd = fwd
        self.log.info('Started Kubectl port forward on port {}'.format(
            self.port))

    def stop(self):
        try:
            if self.fwd:
                self.fwd.kill()
                self.fwd.wait()

                # clear stdout buffer before its gone to not miss out on
                # potential connection errors
                fwd_stdout = [line.decode('utf8') for line in self.fwd.stdout]
                self.log.debug(
                    "Rest of kubectl port forward output was: %s",
                    "".join(fwd_stdout)
                )

                self.fwd = None
        except Exception:
            self.log.exception('Unable to stop kubectl port-forward:')

    def __del__(self):
        try:
            self.stop()
        except Exception:
            self.log.exception('Exception in KubeFwd destructor')
        try:
            super().__del__(self)
        except AttributeError:
            pass


class JobDirPlaybook(object):
    def __init__(self, root):
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
        os.makedirs(self.secrets_root)
        self.secrets = os.path.join(self.secrets_root, 'secrets.yaml')
        self.secrets_content = None

    def addRole(self):
        count = len(self.roles)
        root = os.path.join(self.root, 'role_%i' % (count,))
        os.makedirs(root)
        self.roles.append(root)
        return root


class JobDir(object):
    def __init__(self, root, keep, build_uuid):
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
        #     vars_blacklist.yaml
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
        #     .kube
        #       config
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
        self.root = os.path.realpath(os.path.join(tmpdir, build_uuid))
        os.mkdir(self.root, 0o700)
        self.work_root = os.path.join(self.root, 'work')
        os.makedirs(self.work_root)
        self.src_root = os.path.join(self.work_root, 'src')
        os.makedirs(self.src_root)
        self.log_root = os.path.join(self.work_root, 'logs')
        os.makedirs(self.log_root)
        # Create local tmp directory
        # NOTE(tobiash): This must live within the work root as it can be used
        # by ansible for temporary files which are path checked in untrusted
        # jobs.
        self.local_tmp = os.path.join(self.work_root, 'tmp')
        os.makedirs(self.local_tmp)
        self.ansible_root = os.path.join(self.root, 'ansible')
        os.makedirs(self.ansible_root)
        self.ansible_vars_blacklist = os.path.join(
            self.ansible_root, 'vars_blacklist.yaml')
        with open(self.ansible_vars_blacklist, 'w') as blacklist:
            blacklist.write(json.dumps(BLACKLISTED_VARS))
        self.trusted_root = os.path.join(self.root, 'trusted')
        os.makedirs(self.trusted_root)
        self.untrusted_root = os.path.join(self.root, 'untrusted')
        os.makedirs(self.untrusted_root)
        ssh_dir = os.path.join(self.work_root, '.ssh')
        os.mkdir(ssh_dir, 0o700)
        kube_dir = os.path.join(self.work_root, ".kube")
        os.makedirs(kube_dir)
        self.kubeconfig = os.path.join(kube_dir, "config")
        # Create ansible cache directory
        self.ansible_cache_root = os.path.join(self.root, '.ansible')
        self.fact_cache = os.path.join(self.ansible_cache_root, 'fact-cache')
        os.makedirs(self.fact_cache)
        self.control_path = os.path.join(self.ansible_cache_root, 'cp')
        self.job_unreachable_file = os.path.join(self.ansible_cache_root,
                                                 'nodes.unreachable')
        os.makedirs(self.control_path)

        localhost_facts = os.path.join(self.fact_cache, 'localhost')
        jobtime = datetime.datetime.utcnow()
        date_time_facts = {}
        date_time_facts['year'] = jobtime.strftime('%Y')
        date_time_facts['month'] = jobtime.strftime('%m')
        date_time_facts['weekday'] = jobtime.strftime('%A')
        date_time_facts['weekday_number'] = jobtime.strftime('%w')
        date_time_facts['weeknumber'] = jobtime.strftime('%W')
        date_time_facts['day'] = jobtime.strftime('%d')
        date_time_facts['hour'] = jobtime.strftime('%H')
        date_time_facts['minute'] = jobtime.strftime('%M')
        date_time_facts['second'] = jobtime.strftime('%S')
        date_time_facts['epoch'] = jobtime.strftime('%s')
        date_time_facts['date'] = jobtime.strftime('%Y-%m-%d')
        date_time_facts['time'] = jobtime.strftime('%H:%M:%S')
        date_time_facts['iso8601_micro'] = \
            jobtime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        date_time_facts['iso8601'] = \
            jobtime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        date_time_facts['iso8601_basic'] = jobtime.strftime("%Y%m%dT%H%M%S%f")
        date_time_facts['iso8601_basic_short'] = \
            jobtime.strftime("%Y%m%dT%H%M%S")

        # Set the TZ data manually as jobtime is naive.
        date_time_facts['tz'] = 'UTC'
        date_time_facts['tz_offset'] = '+0000'

        executor_facts = {}
        executor_facts['date_time'] = date_time_facts
        executor_facts['module_setup'] = True

        # NOTE(pabelanger): We do not want to leak zuul-executor facts to other
        # playbooks now that smart fact gathering is enabled by default.  We
        # can have ansible skip populating the cache with information by
        # writing a file with the minimum facts we want.
        with open(localhost_facts, 'w') as f:
            json.dump(executor_facts, f)

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
        self.pre_playbooks = []
        self.post_playbooks = []
        self.cleanup_playbooks = []
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
        os.makedirs(setup_root)
        self.setup_playbook = JobDirPlaybook(setup_root)
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

    def addCleanupPlaybook(self):
        count = len(self.cleanup_playbooks)
        root = os.path.join(
            self.ansible_root, 'cleanup_playbook_%i' % (count,))
        os.makedirs(root)
        playbook = JobDirPlaybook(root)
        self.cleanup_playbooks.append(playbook)
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


class UpdateTask(object):
    def __init__(self, connection_name, project_name, repo_state=None,
                 zuul_event_id=None, build=None):
        self.connection_name = connection_name
        self.project_name = project_name
        self.repo_state = repo_state
        self.canonical_name = None
        self.branches = None
        self.refs = None
        self.event = threading.Event()
        self.success = False

        # These variables are used for log annotation
        self.zuul_event_id = zuul_event_id
        self.build = build

    def __eq__(self, other):
        if (other and other.connection_name == self.connection_name and
            other.project_name == self.project_name and
            other.repo_state == self.repo_state):
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


def is_group_var_set(name, host, args):
    for group in args['groups']:
        if host in group['nodes']:
            group_vars = args['group_vars'].get(group['name'], {})
            if name in group_vars:
                return True
    return False


def make_inventory_dict(nodes, args, all_vars):
    hosts = {}
    for node in nodes:
        hosts[node['name']] = node['host_vars']

    zuul_vars = all_vars['zuul']
    if 'message' in zuul_vars:
        zuul_vars['message'] = base64.b64encode(
            zuul_vars['message'].encode("utf-8")).decode('utf-8')

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


class AnsibleJobContextManager(object, metaclass=abc.ABCMeta):
    """An AnsibleJobContextManager is an object that handles running an
    AnsibleJob within a given context.

    For example, an extension of this may handle placing AnsibleJob into a
    thread or forked process. It may also handle communicating with gearman
    or some other external trigger.

    """

    def __init__(self):
        self.running = False
        self.paused = False
        self.aborted = False
        self.aborted_reason = None
        self.cleanup_started = False
        self.started = False

    def isPaused(self):
        return self.paused

    def isAborted(self):
        return self.aborted

    def setStarted(self, s):
        self.started = s

    @abc.abstractmethod
    def run(self):
        """Run the job"""
        self.running = True

    @abc.abstractmethod
    def pause(self):
        """Pause the job execution
        This may be called from AnsibleJob when a playbook gives zuul the
        directive to pause. This allows the parent process (eg a scheduler)
        to do other events and resume the job when it is ready."""
        pass

    @abc.abstractmethod
    def resume(self):
        """Resume the job execution"""
        pass

    @abc.abstractmethod
    def stop(self):
        """Stop (and abort) the job execution"""
        pass

    @abc.abstractmethod
    def send_aborted(self):
        """Signal job is aborted"""
        pass


class AnsibleJob(object):
    """An object to manage job execution.

    The AnsibleJob is responsible for preparing the workspace and
    executing a single job as a series of playbooks.

    The caller must invoke the prepare procedures before using the
    runPlaybooks procedure to execute a job.
    """
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

    def __init__(self,
                 job_unique,
                 zuul_event_id,
                 context_manager,
                 getMerger,
                 process_worker,
                 merge_root,
                 connections,
                 ansible_manager,
                 execution_wrapper,
                 logger,
                 verbose=False,
                 setup_timeout=60,
                 default_username="zuul",
                 executor_hostname="localhost",
                 executor_extra_paths={},
                 ansible_plugin_dir='',
                 ansible_ara_callbacks=None,
                 ansible_callbacks=None,
                 executor_variables_file=None,
                 statsd=None,
                 log_console_port=DEFAULT_STREAM_PORT):
        self.job_unique = job_unique
        self.zuul_event_id = zuul_event_id
        self.context_manager = context_manager
        self.log = logger
        self.process_worker = process_worker
        self.connections = connections
        self.ansible_manager = ansible_manager
        self.merge_root = merge_root
        self.getMerger = getMerger
        if verbose:
            self.verbosity = '-vvv'
        else:
            self.verbosity = '-v'
        self.setup_timeout = setup_timeout
        self.default_username = default_username
        self.executor_hostname = executor_hostname
        self.statsd = statsd
        self.log_console_port = log_console_port
        self.jobdir = None
        self.project_info = {}
        self.execution_wrapper = execution_wrapper
        self.executor_extra_paths = executor_extra_paths

        self.ara_callbacks = ansible_ara_callbacks
        self.ansible_callbacks = ansible_callbacks
        self.library_dir = os.path.join(ansible_plugin_dir, 'library')
        self.action_dir = os.path.join(ansible_plugin_dir, 'action')
        self.action_dir_general = os.path.join(
            ansible_plugin_dir, 'actiongeneral')
        self.action_dir_trusted = os.path.join(
            ansible_plugin_dir, 'actiontrusted')
        self.callback_dir = os.path.join(ansible_plugin_dir, 'callback')
        self.lookup_dir = os.path.join(ansible_plugin_dir, 'lookup')
        self.filter_dir = os.path.join(ansible_plugin_dir, 'filter')

        self.executor_variables_file = executor_variables_file

        self.cpu_times = {'user': 0, 'system': 0,
                          'children_user': 0, 'children_system': 0}

        self.proc = None
        self.proc_lock = threading.Lock()
        self.extra_env_vars = {}

        self.winrm_key_file = '~/.winrm/winrm_client_cert.key'
        self.winrm_pem_file = '~/.winrm/winrm_client_cert.pem'
        self.winrm_operation_timeout = 'winrm_operation_timeout_sec'
        self.winrm_read_timeout = 'winrm_read_timeout_sec'

    def setWinrmOptions(self, key_file=None, pem_file=None,
                        operation_timeout=None, read_timeout=None):
        if key_file:
            self.winrm_key_file = key_file
        if pem_file:
            self.winrm_pem_file = pem_file
        if operation_timeout:
            self.winrm_operation_timeout = operation_timeout
        if read_timeout:
            self.winrm_read_timeout = read_timeout

    def setJobDir(self, jobdir):
        # The jobdir is managed outside of AnsibleJob along with the cleanup
        # responsibilities. jobdir contents may be modified by other objects.
        self.jobdir = jobdir

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

    def doMergeChanges(self, merger, items, repo_state):
        try:
            ret = merger.mergeChanges(
                items, repo_state=repo_state,
                process_worker=self.process_worker)
        except ValueError:
            self.log.exception("Could not fetch refs to merge from remote")
            raise MergerFetchFailure()
        if not ret:  # merge conflict
            if self.statsd:
                base_key = "zuul.executor.{hostname}.merger"
                self.statsd.incr(base_key + ".FAILURE")
            raise MergerMergeFailure()

        if self.statsd:
            base_key = "zuul.executor.{hostname}.merger"
            self.statsd.incr(base_key + ".SUCCESS")
        recent = ret[3]
        orig_commit = ret[4]
        for key, commit in recent.items():
            (connection, project, branch) = key
            # Compare the commit with the repo state. If it's included in the
            # repo state and it's the same we've set this ref already earlier
            # and don't have to set it again.
            repo_state_project = repo_state.get(
                connection, {}).get(project, {})
            repo_state_commit = repo_state_project.get(
                'refs/heads/%s' % branch)
            if repo_state_commit != commit:
                repo = merger.getRepo(connection, project)
                repo.setRef('refs/heads/' + branch, commit)
        return orig_commit

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

    def getAnsibleTimeout(self, start, timeout):
        if timeout is not None:
            now = time.time()
            elapsed = now - start
            timeout = timeout - elapsed
        return timeout

    def runPlaybooks(self, args, time_starting_build=None):
        result = None
        self.ansible_version = args['ansible_version']

        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write("{now} | Running Ansible setup...\n".format(
                now=datetime.datetime.now()
            ))
        # Run the Ansible 'setup' module on all hosts in the inventory
        # at the start of the job with a 60 second timeout.  If we
        # aren't able to connect to all the hosts and gather facts
        # within that timeout, there is likely a network problem
        # between here and the hosts in the inventory; return them and
        # reschedule the job.
        setup_status, setup_code = self.runAnsibleSetup(
            self.jobdir.setup_playbook, self.ansible_version)
        if setup_status != self.RESULT_NORMAL or setup_code != 0:
            return result

        pre_failed = False
        success = False
        if self.statsd and time_starting_build:
            key = "zuul.executor.{hostname}.starting_builds"
            self.statsd.timing(
                key, (time.monotonic() - time_starting_build) * 1000)

        self.context_manager.setStarted(True)
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
                playbook, ansible_timeout, self.ansible_version, phase='pre',
                index=index)
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
            for index, playbook in enumerate(self.jobdir.playbooks):
                ansible_timeout = self.getAnsibleTimeout(
                    time_started, job_timeout)
                job_status, job_code = self.runAnsiblePlaybook(
                    playbook, ansible_timeout, self.ansible_version,
                    phase='run', index=index)
                if job_status == self.RESULT_ABORTED:
                    return 'ABORTED'
                elif job_status == self.RESULT_TIMED_OUT:
                    # Set the pre-failure flag so this doesn't get
                    # overridden by a post-failure.
                    pre_failed = True
                    result = 'TIMED_OUT'
                    break
                elif job_status == self.RESULT_NORMAL:
                    success = (job_code == 0)
                    if success:
                        result = 'SUCCESS'
                    else:
                        result = 'FAILURE'
                        break
                else:
                    # The result of the job is indeterminate.  Zuul will
                    # run it again.
                    return None

        # check if we need to pause here
        result_data = self.getResultData()
        pause = result_data.get('zuul', {}).get('pause')
        if success and pause:
            self.context_manager.pause()
        if self.context_manager.isAborted():
            return 'ABORTED'

        post_timeout = args['post_timeout']
        unreachable = False
        for index, playbook in enumerate(self.jobdir.post_playbooks):
            # Post timeout operates a little differently to the main job
            # timeout. We give each post playbook the full post timeout to
            # do its job because post is where you'll often record job logs
            # which are vital to understanding why timeouts have happened in
            # the first place.
            post_status, post_code = self.runAnsiblePlaybook(
                playbook, post_timeout, self.ansible_version, success,
                phase='post', index=index)
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

    def setExtraEnvVars(self, env):
        self.extra_env_vars = env

    def runCleanupPlaybooks(self, success):
        if not self.jobdir.cleanup_playbooks:
            return

        # TODO: make this configurable
        cleanup_timeout = 300

        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write("{now} | Running Ansible cleanup...\n".format(
                now=datetime.datetime.now()
            ))

        self.cleanup_started = True
        for index, playbook in enumerate(self.jobdir.cleanup_playbooks):
            self.runAnsiblePlaybook(
                playbook, cleanup_timeout, self.ansible_version,
                success=success, phase='cleanup', index=index)

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
                    ansible_user=self.default_username,
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

                # Ansible >=2.8 introduced "auto" as an
                # ansible_python_interpreter argument that looks up
                # which python to use on the remote host in an inbuilt
                # table and essentially "does the right thing"
                # (i.e. chooses python3 on 3-only hosts like later
                # Fedoras).
                # If ansible_python_interpreter is set either as a group
                # var or all-var, then don't do anything here; let the
                # user control.
                api = 'ansible_python_interpreter'
                if (api not in args['vars'] and
                    not is_group_var_set(api, name, args)):
                    python = node.get('python_path', 'auto')
                    host_vars.setdefault(api, python)

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
                    elif connection_type == "kubectl":
                        host_vars['ansible_kubectl_context'] = \
                            node.get('kubectl_context')

                shell_type = node.get('shell_type')
                if shell_type:
                    host_vars['ansible_shell_type'] = shell_type

                host_keys = []
                for key in node.get('host_keys', []):
                    if port != 22:
                        host_keys.append("[%s]:%s %s" % (ip, port, key))
                    else:
                        host_keys.append("%s %s" % (ip, key))
                if not node.get('host_keys'):
                    host_vars['ansible_ssh_common_args'] = \
                        '-o StrictHostKeyChecking=false'

                hosts.append(dict(
                    name=name,
                    host_vars=host_vars,
                    host_keys=host_keys))
        return hosts

    def _blockPluginDirs(self, path):
        '''Prevent execution of playbooks or roles with plugins

        Plugins are loaded from roles and also if there is a plugin
        dir adjacent to the playbook.  Throw an error if the path
        contains a location that would cause a plugin to get loaded.

        '''
        for entry in os.listdir(path):
            entry = os.path.join(path, entry)
            if os.path.isdir(entry) and entry.endswith('_plugins'):
                raise PluginFoundError(
                    "Ansible plugin dir %s found adjacent to playbook %s in "
                    "non-trusted repo." % (entry, path))

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

        job_playbook = None
        for playbook in args['playbooks']:
            jobdir_playbook = self.jobdir.addPlaybook()
            self.preparePlaybook(jobdir_playbook, playbook, args)
            if jobdir_playbook.path is not None:
                if job_playbook is None:
                    job_playbook = jobdir_playbook

        if job_playbook is None:
            raise ExecutorError("No playbook specified")

        for playbook in args['post_playbooks']:
            jobdir_playbook = self.jobdir.addPostPlaybook()
            self.preparePlaybook(jobdir_playbook, playbook, args)

        for playbook in args['cleanup_playbooks']:
            jobdir_playbook = self.jobdir.addCleanupPlaybook()
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
            merger = self.getMerger(root, self.merge_root, self.log)
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
                    merger = self.getMerger(
                        root,
                        self.jobdir.src_root,
                        self.log)
                    break

            if merger is None:
                merger = self.getMerger(root, self.merge_root, self.log)

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
        source = self.connections.getSource(role['connection'])
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
            raise ExecutorError("Invalid role name %s" % name)
        os.symlink(path, link)

        try:
            role_path = self.findRole(link, trusted=jobdir_playbook.trusted)
        except RoleNotFoundError:
            if role['implicit']:
                self.log.debug("Implicit role not found in %s", link)
                return
            raise
        except PluginFoundError:
            if role['implicit']:
                self.log.info("Not adding implicit role %s due to "
                              "plugin", link)
                return
            raise
        if role_path is None:
            # In the case of a bare role, add the containing directory
            role_path = root
        self.log.debug("Adding role path %s", role_path)
        jobdir_playbook.roles_path.append(role_path)

    def prepareKubeConfig(self, jobdir, data):
        kube_cfg_path = jobdir.kubeconfig
        if os.path.exists(kube_cfg_path):
            kube_cfg = yaml.safe_load(open(kube_cfg_path))
        else:
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

        # Do not add a cluster/server that already exists in the kubeconfig
        # because that leads to 'duplicate name' errors on multi-node builds.
        # Also, as the cluster name directly corresponds to a server, there
        # is no need to add it twice.
        if cluster_name not in [c['name'] for c in kube_cfg['clusters']]:
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
        all_vars['zuul'] = args['zuul'].copy()
        all_vars['zuul']['executor'] = dict(
            hostname=self.executor_hostname,
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
                self.prepareKubeConfig(self.jobdir, data)
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
                    fwd = KubeFwd(zuul_event_id=self.zuul_event_id,
                                  build=self.job_unique,
                                  kubeconfig=self.jobdir.kubeconfig,
                                  context=data['context_name'],
                                  namespace=data['namespace'],
                                  pod=data['pod'])
                    try:
                        fwd.start()
                        self.port_forwards.append(fwd)
                        all_vars['zuul']['resources'][
                            node['name'][0]]['stream_port'] = fwd.port
                    except Exception:
                        self.log.exception("Unable to start port forward:")
                        self.log.error("Kubectl and socat are required for "
                                       "streaming logs")

        # Remove resource node from nodes list
        for node in resources_nodes:
            args['nodes'].remove(node)

        nodes = self.getHostList(args)
        setup_inventory = make_setup_inventory_dict(nodes)
        inventory = make_inventory_dict(nodes, args, all_vars)

        with open(self.jobdir.setup_inventory, 'w') as setup_inventory_yaml:
            setup_inventory_yaml.write(
                yaml.safe_dump(setup_inventory, default_flow_style=False))

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

    def writeAnsibleConfig(self, jobdir_playbook):
        trusted = jobdir_playbook.trusted

        # TODO(mordred) This should likely be extracted into a more generalized
        #               mechanism for deployers being able to add callback
        #               plugins.
        if self.ara_callbacks:
            callback_path = '%s:%s' % (
                self.callback_dir,
                os.path.dirname(self.ara_callbacks))
        else:
            callback_path = self.callback_dir
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
                         % self.library_dir)
            config.write('command_warnings = False\n')
            config.write('callback_plugins = %s\n' % callback_path)
            config.write('stdout_callback = zuul_stream\n')
            config.write('filter_plugins = %s\n'
                         % self.filter_dir)
            config.write('nocows = True\n')  # save useless stat() calls
            # bump the timeout because busy nodes may take more than
            # 10s to respond
            config.write('timeout = 30\n')

            # We need the general action dir to make the zuul_return plugin
            # available to every job.
            action_dirs = [self.action_dir_general]
            if not trusted:
                # Untrusted jobs add the action dir which makes sure localhost
                # modules are restricted where needed. Further the command
                # plugin needs to be restricted and also inject zuul_log_id
                # to make log streaming work.
                action_dirs.append(self.action_dir)
                config.write('lookup_plugins = %s\n'
                             % self.lookup_dir)
            else:
                # Trusted jobs add the actiontrusted dir which adds the
                # unrestricted command plugin to inject zuul_log_id to make
                # log streaming work.
                action_dirs.append(self.action_dir_trusted)

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

            if self.ansible_callbacks:
                config.write('callback_whitelist =\n')
                for callback in self.ansible_callbacks.keys():
                    config.write('    %s,\n' % callback)

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

            if self.ansible_callbacks:
                for cb_name, cb_config in self.ansible_callbacks.items():
                    config.write("[callback_%s]\n" % cb_name)
                    for k, n in cb_config.items():
                        config.write("%s = %s\n" % (k, n))

    def _ansibleTimeout(self, msg):
        self.log.warning(msg)
        self.abortRunningProc()

    def abortRunningProc(self):
        with self.proc_lock:
            if self.proc and not self.context_manager.cleanup_started:
                self.log.debug("Abort: sending kill signal to job "
                               "process group")
                try:
                    pgid = os.getpgid(self.proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    self.log.exception(
                        "Exception while killing ansible process:")
            elif self.proc and self.cleanup_started:
                self.log.debug("Abort: cleanup is in progress")
            else:
                self.log.debug("Abort: no process is running")

    def runAnsible(self, cmd, timeout, playbook, ansible_version,
                   wrapped=True, cleanup=False):
        config_file = playbook.ansible_config
        env_copy = {key: value
                    for key, value in os.environ.copy().items()
                    if not key.startswith("ZUUL_")}
        env_copy.update(self.extra_env_vars)
        if self.ara_callbacks:
            env_copy['ARA_LOG_CONFIG'] = self.jobdir.logging_json
        env_copy['ZUUL_JOB_LOG_CONFIG'] = self.jobdir.logging_json
        env_copy['ZUUL_JOBDIR'] = self.jobdir.root
        if self.log_console_port != DEFAULT_STREAM_PORT:
            env_copy['ZUUL_CONSOLE_PORT'] = str(self.log_console_port)
        env_copy['TMP'] = self.jobdir.local_tmp
        pythonpath = env_copy.get('PYTHONPATH')
        if pythonpath:
            pythonpath = [pythonpath]
        else:
            pythonpath = []

        ansible_dir = self.ansible_manager.getAnsibleDir(
            ansible_version)
        pythonpath = [ansible_dir] + pythonpath
        env_copy['PYTHONPATH'] = os.path.pathsep.join(pythonpath)

        if playbook.trusted:
            paths = self.executor_extra_paths.get('trusted', {})
        else:
            paths = self.executor_extra_paths.get('untrusted', {})
        ro_paths = copy.copy(paths.get('ro', []))
        rw_paths = copy.copy(paths.get('rw', []))

        ro_paths.append(ansible_dir)
        ro_paths.append(
            self.ansible_manager.getAnsibleInstallDir(ansible_version))
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
            wrapper = self.execution_wrapper
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
            if self.context_manager.isAborted() and not cleanup:
                return (self.RESULT_ABORTED, None)
            self.log.debug("Ansible command: ANSIBLE_CONFIG=%s ZUUL_JOBDIR=%s "
                           "ZUUL_JOB_LOG_CONFIG=%s PYTHONPATH=%s TMP=%s %s",
                           env_copy['ANSIBLE_CONFIG'],
                           env_copy['ZUUL_JOBDIR'],
                           env_copy['ZUUL_JOB_LOG_CONFIG'],
                           env_copy['PYTHONPATH'],
                           env_copy['TMP'],
                           " ".join(shlex.quote(c) for c in cmd))
            self.proc = popen(
                cmd,
                cwd=self.jobdir.work_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env_copy,
            )

        syntax_buffer = []
        ret = None
        if timeout:
            watchdog = Watchdog(timeout, self._ansibleTimeout,
                                ("Ansible timeout exceeded: %s" % timeout,))
            watchdog.start()
        try:
            ansible_log = get_annotated_logger(
                logging.getLogger("zuul.AnsibleJob.output"),
                self.zuul_event_id, build=self.job_unique)

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
                ansible_log.debug("Ansible output: %s" % (line,))
            self.log.debug("Ansible output terminated")
            try:
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
            except psutil.NoSuchProcess:
                self.log.warn("Cannot get cpu_times for process %d. Is your"
                              "/proc mounted with hidepid=2"
                              " on an old linux kernel?", self.proc.pid)
            ret = self.proc.wait()
            self.log.debug("Ansible exit code: %s" % (ret,))
        finally:
            if timeout:
                watchdog.stop()
                self.log.debug("Stopped watchdog")
            self.log.debug("Stopped disk job killer")

        with self.proc_lock:
            self.proc.stdout.close()
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
        elif ret == 2:
            with open(self.jobdir.job_output_file, 'a') as job_output:
                found_marker = False
                for line in syntax_buffer:
                    # This is a workaround to detect winrm connection failures
                    # that are not detected by ansible. These can be detected
                    # if the string 'FATAL ERROR DURING FILE TRANSFER' is in
                    # the ansible output. In this case we should treat the
                    # host as unreachable and retry the job.
                    if b'FATAL ERROR DURING FILE TRANSFER' in line:
                        return self.RESULT_UNREACHABLE, None

                    # Extract errors for special cases that are treated like
                    # task errors by Ansible (e.g. missing role when using
                    # 'include_role').
                    if line.startswith(b'ERROR!'):
                        found_marker = True
                    if not found_marker:
                        continue
                    job_output.write("{now} | {line}\n".format(
                        now=datetime.datetime.now(),
                        line=line.decode('utf-8').rstrip()))

        if self.context_manager.isAborted():
            return (self.RESULT_ABORTED, None)

        return (self.RESULT_NORMAL, ret)

    def runAnsibleSetup(self, playbook, ansible_version):
        ansible = self.ansible_manager.getAnsibleCommand(
            ansible_version, command='ansible')
        cmd = [ansible, '*', self.verbosity, '-m', 'setup',
               '-i', self.jobdir.setup_inventory,
               '-a', 'gather_subset=!all']
        if self.executor_variables_file is not None:
            cmd.extend(['-e@%s' % self.executor_variables_file])

        result, code = self.runAnsible(
            cmd=cmd, timeout=self.setup_timeout,
            playbook=playbook, ansible_version=ansible_version, wrapped=False)
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.statsd:
            base_key = "zuul.executor.{hostname}.phase.setup"
            self.statsd.incr(base_key + ".%s" % self.RESULT_MAP[result])
        return result, code

    def prepareRepositories(self, update_manager, args):
        tasks = []
        projects = set()
        repo_state = args['repo_state']

        # Make sure all projects used by the job are updated...
        for project in args['projects']:
            self.log.debug("Updating project %s" % (project,))
            tasks.append(update_manager(
                project['connection'], project['name'],
                repo_state=repo_state,
                zuul_event_id=self.zuul_event_id,
                build=self.job_unique))
            projects.add((project['connection'], project['name']))

        # ...as well as all playbook and role projects.
        repos = []
        playbooks = (args['pre_playbooks'] + args['playbooks'] +
                     args['post_playbooks'] + args['cleanup_playbooks'])
        for playbook in playbooks:
            repos.append(playbook)
            repos += playbook['roles']

        for repo in repos:
            key = (repo['connection'], repo['project'])
            if key not in projects:
                self.log.debug("Updating playbook or role %s" % (
                               repo['project'],))
                tasks.append(update_manager(
                    *key, repo_state=repo_state,
                    zuul_event_id=self.zuul_event_id,
                    build=self.job_unique))
                projects.add(key)

        for task in tasks:
            task.wait()

            if not task.success:
                raise ExecutorError(
                    'Failed to update project %s' % task.canonical_name)

            self.project_info[task.canonical_name] = {
                'refs': task.refs,
                'branches': task.branches,
            }

        # Early abort if abort requested
        if self.context_manager.isAborted():
            self.context_manager.send_aborted()
            return False, None

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
            item_commit = self.doMergeChanges(
                merger, merge_items, repo_state)
            if item_commit is None:
                # Merge failures are raised, so if we get here something else
                # has gone wrong
                return False, merger

        # Early abort if abort requested
        if self.context_manager.isAborted():
            self.context_manager.send_aborted()
            return False, merger

        state_items = [i for i in args['items'] if not i.get('number')]
        if state_items:
            merger.setRepoState(
                state_items, repo_state,
                process_worker=self.process_worker)

        # Early abort if abort requested
        if self.context_manager.isAborted():
            self.context_manager.send_aborted()
            return False, merger

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

    def runAnsibleCleanup(self, playbook):
        # TODO(jeblair): This requires a bugfix in Ansible 2.4
        # Once this is used, increase the controlpersist timeout.
        return (self.RESULT_NORMAL, 0)

        cmd = ['ansible', '*', self.verbosity, '-m', 'meta',
               '-a', 'reset_connection']

        result, code = self.runAnsible(
            cmd=cmd, timeout=60, playbook=playbook,
            wrapped=False)
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.statsd:
            base_key = "zuul.executor.{hostname}.phase.cleanup"
            self.statsd.incr(base_key + ".%s" % self.RESULT_MAP[result])
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

    def runAnsiblePlaybook(self, playbook, timeout, ansible_version,
                           success=None, phase=None, index=None):
        cmd = [self.ansible_manager.getAnsibleCommand(
            ansible_version), self.verbosity, playbook.path]
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

        if not playbook.trusted:
            cmd.extend(['-e', '@' + self.jobdir.ansible_vars_blacklist])

        self.emitPlaybookBanner(playbook, 'START', phase)

        result, code = self.runAnsible(cmd, timeout, playbook, ansible_version,
                                       cleanup=phase == 'cleanup')
        self.log.debug("Ansible complete, result %s code %s" % (
            self.RESULT_MAP[result], code))
        if self.statsd:
            base_key = "zuul.executor.{hostname}.phase.{phase}"
            self.statsd.incr(
                base_key + ".{result}",
                result=self.RESULT_MAP[result],
                phase=phase or 'unknown')

        self.emitPlaybookBanner(playbook, 'END', phase, result=result)
        return result, code


def construct_gearman_params(uuid, sched, nodeset, job, item, pipeline,
                             dependent_changes=[], merger_items=[],
                             redact_secrets_and_keys=True):
    """Returns a list of all the parameters needed to build a job.

    These parameters may be passed to zuul-executors (via gearman) to perform
    the job itself.

    Alternatively they contain enough information to load into another build
    environment - for example, a local runner.
    """
    tenant = pipeline.tenant
    project = dict(
        name=item.change.project.name,
        short_name=item.change.project.name.split('/')[-1],
        canonical_hostname=item.change.project.canonical_hostname,
        canonical_name=item.change.project.canonical_name,
        src_dir=os.path.join('src', item.change.project.canonical_name),
    )

    zuul_params = dict(
        build=uuid,
        buildset=item.current_build_set.uuid,
        ref=item.change.ref,
        pipeline=pipeline.name,
        post_review=pipeline.post_review,
        job=job.name,
        voting=job.voting,
        project=project,
        tenant=tenant.name,
        timeout=job.timeout,
        event_id=item.event.zuul_event_id if item.event else None,
        jobtags=sorted(job.tags),
        _inheritance_path=list(job.inheritance_path))
    if job.artifact_data:
        zuul_params['artifacts'] = job.artifact_data
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
    if hasattr(item.change, 'message'):
        zuul_params['message'] = item.change.message
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
    params['ansible_version'] = job.ansible_version

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
        params['cleanup_playbooks'] = [make_playbook(x)
                                       for x in job.cleanup_run]

    nodes = []
    for node in nodeset.getNodes():
        n = node.toDict()
        n.update(dict(name=node.name, label=node.label))
        nodes.append(n)
    params['nodes'] = nodes
    params['groups'] = [group.toDict() for group in nodeset.getGroups()]
    params['ssh_keys'] = []
    if pipeline.post_review:
        if redact_secrets_and_keys:
            ssh_key = "REDACTED"
        else:
            ssh_key = item.change.project.private_ssh_key
        params['ssh_keys'].append(dict(
            name='%s project key' % item.change.project.canonical_name,
            key=ssh_key))
    params['vars'] = job.combined_variables
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

    if item.event:
        params['zuul_event_id'] = item.event.zuul_event_id
    return params
