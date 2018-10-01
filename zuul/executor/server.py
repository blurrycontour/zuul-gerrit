# Copyright 2014 OpenStack Foundation
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

import datetime
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
import traceback

from zuul.lib.config import get_default
from zuul.lib.statsd import get_statsd

import gear

import zuul.merger.merger
import zuul.ansible.logconfig
from zuul.executor.common import AnsibleJobBase
from zuul.executor.common import AnsibleJobLogAdapter
from zuul.executor.common import DeduplicateQueue
from zuul.executor.common import DEFAULT_FINGER_PORT
from zuul.executor.common import ExecutorError
from zuul.executor.common import JobDir
from zuul.executor.common import SshAgent
from zuul.executor.common import UpdateTask
from zuul.executor.sensors.cpu import CPUSensor
from zuul.executor.sensors.hdd import HDDSensor
from zuul.executor.sensors.pause import PauseSensor
from zuul.executor.sensors.startingbuilds import StartingBuildsSensor
from zuul.executor.sensors.ram import RAMSensor
from zuul.lib import commandsocket

COMMANDS = ['stop', 'pause', 'unpause', 'graceful', 'verbose',
            'unverbose', 'keep', 'nokeep']


class StopException(Exception):
    """An exception raised when an inner loop is asked to stop."""
    pass


class DiskAccountant(object):
    ''' A single thread to periodically run du and monitor a base directory

    Whenever the accountant notices a dir over limit, it will call the
    given func with an argument of the job directory. That function
    should be used to remediate the problem, generally by killing the
    job producing the disk bloat). The function will be called every
    time the problem is noticed, so it should be handled synchronously
    to avoid stacking up calls.
    '''
    log = logging.getLogger("zuul.ExecutorDiskAccountant")

    def __init__(self, jobs_base, limit, func, cache_dir, usage_func=None):
        '''
        :param str jobs_base: absolute path name of dir to be monitored
        :param int limit: maximum number of MB allowed to be in use in any one
                          subdir
        :param callable func: Function to call with overlimit dirs
        :param str cache_dir: absolute path name of dir to be passed as the
                              first argument to du. This will ensure du does
                              not count any hardlinks to files in this
                              directory against a single job.
        :param callable usage_func: Optional function to call with usage
                                    for every dir _NOT_ over limit
        '''
        # Don't cross the streams
        if cache_dir == jobs_base:
            raise Exception("Cache dir and jobs dir cannot be the same")
        self.thread = threading.Thread(target=self._run,
                                       name='diskaccountant')
        self.thread.daemon = True
        self._running = False
        self.jobs_base = jobs_base
        self.limit = limit
        self.func = func
        self.cache_dir = cache_dir
        self.usage_func = usage_func
        self.stop_event = threading.Event()

    def _run(self):
        while self._running:
            # Walk job base
            before = time.time()
            du = subprocess.Popen(
                ['du', '-m', '--max-depth=1', self.cache_dir, self.jobs_base],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            for line in du.stdout:
                (size, dirname) = line.rstrip().split()
                dirname = dirname.decode('utf8')
                if dirname == self.jobs_base or dirname == self.cache_dir:
                    continue
                if os.path.dirname(dirname) == self.cache_dir:
                    continue
                size = int(size)
                if size > self.limit:
                    self.log.info(
                        "{job} is using {size}MB (limit={limit})"
                        .format(size=size, job=dirname, limit=self.limit))
                    self.func(dirname)
                elif self.usage_func:
                    self.log.debug(
                        "{job} is using {size}MB (limit={limit})"
                        .format(size=size, job=dirname, limit=self.limit))
                    self.usage_func(dirname, size)
            du.wait()
            after = time.time()
            # Sleep half as long as that took, or 1s, whichever is longer
            delay_time = max((after - before) / 2, 1.0)
            self.stop_event.wait(delay_time)

    def start(self):
        self._running = True
        self.thread.start()

    def stop(self):
        self._running = False
        self.stop_event.set()
        # We join here to avoid whitelisting the thread -- if it takes more
        # than 5s to stop in tests, there's a problem.
        self.thread.join(timeout=5)


def _copy_ansible_files(python_module, target_dir):
        library_path = os.path.dirname(os.path.abspath(python_module.__file__))
        for fn in os.listdir(library_path):
            if fn == "__pycache__":
                continue
            full_path = os.path.join(library_path, fn)
            if os.path.isdir(full_path):
                shutil.copytree(full_path, os.path.join(target_dir, fn))
            else:
                shutil.copy(os.path.join(library_path, fn), target_dir)


class AnsibleJob(AnsibleJobBase):
    def __init__(self, executor_server, job):
        logger = logging.getLogger("zuul.AnsibleJob")
        self.log = AnsibleJobLogAdapter(logger, {'job': job.unique})
        self.executor_server = executor_server
        self.job = job
        self.arguments = json.loads(job.arguments)
        self.jobdir = None
        self.proc = None
        self.proc_lock = threading.Lock()
        self.running = False
        self.started = False  # Whether playbooks have started running
        self.time_starting_build = None
        self.paused = False
        self.aborted = False
        self.aborted_reason = None
        self._resume_event = threading.Event()
        self.thread = None
        self.project_info = {}
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

        self.executor_variables_file = None

        self.cpu_times = {'user': 0, 'system': 0,
                          'children_user': 0, 'children_system': 0}

        if self.executor_server.config.has_option('executor', 'variables'):
            self.executor_variables_file = self.executor_server.config.get(
                'executor', 'variables')

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
        tasks = []
        projects = set()

        # Make sure all projects used by the job are updated...
        for project in args['projects']:
            self.log.debug("Updating project %s" % (project,))
            tasks.append(self.executor_server.update(
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
                tasks.append(self.executor_server.update(*key))
                projects.add(key)

        for task in tasks:
            task.wait()
            self.project_info[task.canonical_name] = {
                'refs': task.refs,
                'branches': task.branches,
            }

        self.log.debug("Git updates complete")
        merger = self.executor_server._getMerger(
            self.jobdir.src_root,
            self.executor_server.merge_root,
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
            item_commit = self.doMergeChanges(merger, merge_items,
                                              args['repo_state'])
            if item_commit is None:
                # There was a merge conflict and we have already sent
                # a work complete result, don't run any jobs
                return

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


class ExecutorMergeWorker(gear.TextWorker):
    def __init__(self, executor_server, *args, **kw):
        self.zuul_executor_server = executor_server
        super(ExecutorMergeWorker, self).__init__(*args, **kw)

    def handleNoop(self, packet):
        # Wait until the update queue is empty before responding
        while self.zuul_executor_server.update_queue.qsize():
            time.sleep(1)

        with self.zuul_executor_server.merger_lock:
            super(ExecutorMergeWorker, self).handleNoop(packet)


class ExecutorExecuteWorker(gear.TextWorker):
    def __init__(self, executor_server, *args, **kw):
        self.zuul_executor_server = executor_server
        super(ExecutorExecuteWorker, self).__init__(*args, **kw)

    def handleNoop(self, packet):
        # Delay our response to running a new job based on the number
        # of jobs we're currently running, in an attempt to spread
        # load evenly among executors.
        workers = len(self.zuul_executor_server.job_workers)
        delay = (workers ** 2) / 1000.0
        time.sleep(delay)
        return super(ExecutorExecuteWorker, self).handleNoop(packet)


class ExecutorServer(object):
    log = logging.getLogger("zuul.ExecutorServer")
    _job_class = AnsibleJob

    def __init__(self, config, connections={}, jobdir_root=None,
                 keep_jobdir=False, log_streaming_port=DEFAULT_FINGER_PORT):
        self.config = config
        self.keep_jobdir = keep_jobdir
        self.jobdir_root = jobdir_root
        # TODOv3(mordred): make the executor name more unique --
        # perhaps hostname+pid.
        self.hostname = get_default(self.config, 'executor', 'hostname',
                                    socket.getfqdn())
        self.log_streaming_port = log_streaming_port
        self.merger_lock = threading.Lock()
        self.governor_lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.verbose = False
        self.command_map = dict(
            stop=self.stop,
            pause=self.pause,
            unpause=self.unpause,
            graceful=self.graceful,
            verbose=self.verboseOn,
            unverbose=self.verboseOff,
            keep=self.keep,
            nokeep=self.nokeep,
        )

        statsd_extra_keys = {'hostname': self.hostname}
        self.statsd = get_statsd(config, statsd_extra_keys)
        self.merge_root = get_default(self.config, 'executor', 'git_dir',
                                      '/var/lib/zuul/executor-git')
        self.default_username = get_default(self.config, 'executor',
                                            'default_username', 'zuul')
        self.disk_limit_per_job = int(get_default(self.config, 'executor',
                                                  'disk_limit_per_job', 250))
        self.zone = get_default(self.config, 'executor', 'zone')
        self.merge_email = get_default(self.config, 'merger', 'git_user_email')
        self.merge_name = get_default(self.config, 'merger', 'git_user_name')
        self.merge_speed_limit = get_default(
            config, 'merger', 'git_http_low_speed_limit', '1000')
        self.merge_speed_time = get_default(
            config, 'merger', 'git_http_low_speed_time', '30')
        # If the execution driver ever becomes configurable again,
        # this is where it would happen.
        execution_wrapper_name = 'bubblewrap'
        self.accepting_work = False
        self.execution_wrapper = connections.drivers[execution_wrapper_name]

        self.connections = connections
        # This merger and its git repos are used to maintain
        # up-to-date copies of all the repos that are used by jobs, as
        # well as to support the merger:cat functon to supply
        # configuration information to Zuul when it starts.
        self.merger = self._getMerger(self.merge_root, None)
        self.update_queue = DeduplicateQueue()

        command_socket = get_default(
            self.config, 'executor', 'command_socket',
            '/var/lib/zuul/executor.socket')
        self.command_socket = commandsocket.CommandSocket(command_socket)

        state_dir = get_default(self.config, 'executor', 'state_dir',
                                '/var/lib/zuul', expand_user=True)
        ansible_dir = os.path.join(state_dir, 'ansible')
        self.ansible_dir = ansible_dir
        if os.path.exists(ansible_dir):
            shutil.rmtree(ansible_dir)

        zuul_dir = os.path.join(ansible_dir, 'zuul')
        plugin_dir = os.path.join(zuul_dir, 'ansible')

        os.makedirs(plugin_dir, mode=0o0755)

        self.library_dir = os.path.join(plugin_dir, 'library')
        self.action_dir = os.path.join(plugin_dir, 'action')
        self.action_dir_general = os.path.join(plugin_dir, 'actiongeneral')
        self.callback_dir = os.path.join(plugin_dir, 'callback')
        self.lookup_dir = os.path.join(plugin_dir, 'lookup')
        self.filter_dir = os.path.join(plugin_dir, 'filter')

        _copy_ansible_files(zuul.ansible, plugin_dir)

        # We're copying zuul.ansible.* into a directory we are going
        # to add to pythonpath, so our plugins can "import
        # zuul.ansible".  But we're not installing all of zuul, so
        # create a __init__.py file for the stub "zuul" module.
        with open(os.path.join(zuul_dir, '__init__.py'), 'w'):
            pass

        # If keep is not set, ensure the job dir is empty on startup,
        # in case we were uncleanly shut down.
        if not self.keep_jobdir:
            for fn in os.listdir(self.jobdir_root):
                if not os.path.isdir(fn):
                    continue
                self.log.info("Deleting stale jobdir %s", fn)
                shutil.rmtree(os.path.join(self.jobdir_root, fn))

        self.job_workers = {}
        self.disk_accountant = DiskAccountant(self.jobdir_root,
                                              self.disk_limit_per_job,
                                              self.stopJobDiskFull,
                                              self.merge_root)

        self.pause_sensor = PauseSensor()
        cpu_sensor = CPUSensor(config)
        self.sensors = [
            cpu_sensor,
            HDDSensor(config),
            self.pause_sensor,
            RAMSensor(config),
            StartingBuildsSensor(self, cpu_sensor.max_load_avg)
        ]

    def _getMerger(self, root, cache_root, logger=None):
        return zuul.merger.merger.Merger(
            root, self.connections, self.merge_email, self.merge_name,
            self.merge_speed_limit, self.merge_speed_time, cache_root, logger,
            execution_context=True)

    def start(self):
        self._running = True
        self._command_running = True
        server = self.config.get('gearman', 'server')
        port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        self.merger_worker = ExecutorMergeWorker(self, 'Zuul Executor Merger')
        self.merger_worker.addServer(server, port, ssl_key, ssl_cert, ssl_ca)
        self.executor_worker = ExecutorExecuteWorker(
            self, 'Zuul Executor Server')
        self.executor_worker.addServer(server, port, ssl_key, ssl_cert, ssl_ca)
        self.log.debug("Waiting for server")
        self.merger_worker.waitForServer()
        self.executor_worker.waitForServer()
        self.log.debug("Registering")
        self.register()

        self.log.debug("Starting command processor")
        self.command_socket.start()
        self.command_thread = threading.Thread(target=self.runCommand,
                                               name='command')
        self.command_thread.daemon = True
        self.command_thread.start()

        self.log.debug("Starting worker")
        self.update_thread = threading.Thread(target=self._updateLoop,
                                              name='update')
        self.update_thread.daemon = True
        self.update_thread.start()
        self.merger_thread = threading.Thread(target=self.run_merger,
                                              name='merger')
        self.merger_thread.daemon = True
        self.merger_thread.start()
        self.executor_thread = threading.Thread(target=self.run_executor,
                                                name='executor')
        self.executor_thread.daemon = True
        self.executor_thread.start()
        self.governor_stop_event = threading.Event()
        self.governor_thread = threading.Thread(target=self.run_governor,
                                                name='governor')
        self.governor_thread.daemon = True
        self.governor_thread.start()
        self.disk_accountant.start()

    def register(self):
        self.register_work()
        self.executor_worker.registerFunction("executor:resume:%s" %
                                              self.hostname)
        self.executor_worker.registerFunction("executor:stop:%s" %
                                              self.hostname)
        self.merger_worker.registerFunction("merger:merge")
        self.merger_worker.registerFunction("merger:cat")
        self.merger_worker.registerFunction("merger:refstate")
        self.merger_worker.registerFunction("merger:fileschanges")

    def register_work(self):
        if self._running:
            self.accepting_work = True
            function_name = 'executor:execute'
            if self.zone:
                function_name += ':%s' % self.zone
            self.executor_worker.registerFunction(function_name)
            # TODO(jeblair): Update geard to send a noop after
            # registering for a job which is in the queue, then remove
            # this API violation.
            self.executor_worker._sendGrabJobUniq()

    def unregister_work(self):
        self.accepting_work = False
        function_name = 'executor:execute'
        if self.zone:
            function_name += ':%s' % self.zone
        self.executor_worker.unRegisterFunction(function_name)

    def stop(self):
        self.log.debug("Stopping")
        self.disk_accountant.stop()
        # The governor can change function registration, so make sure
        # it has stopped.
        self.governor_stop_event.set()
        self.governor_thread.join()
        # Stop accepting new jobs
        self.merger_worker.setFunctions([])
        self.executor_worker.setFunctions([])
        # Tell the executor worker to abort any jobs it just accepted,
        # and grab the list of currently running job workers.
        with self.run_lock:
            self._running = False
            self._command_running = False
            workers = list(self.job_workers.values())

        for job_worker in workers:
            try:
                job_worker.stop()
            except Exception:
                self.log.exception("Exception sending stop command "
                                   "to worker:")
        for job_worker in workers:
            try:
                job_worker.wait()
            except Exception:
                self.log.exception("Exception waiting for worker "
                                   "to stop:")

        # Now that we aren't accepting any new jobs, and all of the
        # running jobs have stopped, tell the update processor to
        # stop.
        self.update_queue.put(None)

        # All job results should have been sent by now, shutdown the
        # gearman workers.
        self.merger_worker.shutdown()
        self.executor_worker.shutdown()

        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.gauge(base_key + '.load_average', 0)
            self.statsd.gauge(base_key + '.pct_used_ram', 0)
            self.statsd.gauge(base_key + '.running_builds', 0)

        self.command_socket.stop()
        self.log.debug("Stopped")

    def join(self):
        self.governor_thread.join()
        self.update_thread.join()
        self.merger_thread.join()
        self.executor_thread.join()

    def pause(self):
        self.pause_sensor.pause = True

    def unpause(self):
        self.pause_sensor.pause = False

    def graceful(self):
        # TODOv3: implement
        pass

    def verboseOn(self):
        self.verbose = True

    def verboseOff(self):
        self.verbose = False

    def keep(self):
        self.keep_jobdir = True

    def nokeep(self):
        self.keep_jobdir = False

    def runCommand(self):
        while self._command_running:
            try:
                command = self.command_socket.get().decode('utf8')
                if command != '_stop':
                    self.command_map[command]()
            except Exception:
                self.log.exception("Exception while processing command")

    def _updateLoop(self):
        while True:
            try:
                self._innerUpdateLoop()
            except StopException:
                return
            except Exception:
                self.log.exception("Exception in update thread:")

    def _innerUpdateLoop(self):
        # Inside of a loop that keeps the main repositories up to date
        task = self.update_queue.get()
        if task is None:
            # We are asked to stop
            raise StopException()
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

    def run_merger(self):
        self.log.debug("Starting merger listener")
        while self._running:
            try:
                job = self.merger_worker.getJob()
                try:
                    self.mergerJobDispatch(job)
                except Exception:
                    self.log.exception("Exception while running job")
                    job.sendWorkException(
                        traceback.format_exc().encode('utf8'))
            except gear.InterruptedError:
                pass
            except Exception:
                self.log.exception("Exception while getting job")

    def mergerJobDispatch(self, job):
        if job.name == 'merger:cat':
            self.log.debug("Got cat job: %s" % job.unique)
            self.cat(job)
        elif job.name == 'merger:merge':
            self.log.debug("Got merge job: %s" % job.unique)
            self.merge(job)
        elif job.name == 'merger:refstate':
            self.log.debug("Got refstate job: %s" % job.unique)
            self.refstate(job)
        elif job.name == 'merger:fileschanges':
            self.log.debug("Got fileschanges job: %s" % job.unique)
            self.fileschanges(job)
        else:
            self.log.error("Unable to handle job %s" % job.name)
            job.sendWorkFail()

    def run_executor(self):
        self.log.debug("Starting executor listener")
        while self._running:
            try:
                job = self.executor_worker.getJob()
                try:
                    self.executorJobDispatch(job)
                except Exception:
                    self.log.exception("Exception while running job")
                    job.sendWorkException(
                        traceback.format_exc().encode('utf8'))
            except gear.InterruptedError:
                pass
            except Exception:
                self.log.exception("Exception while getting job")

    def executorJobDispatch(self, job):
        with self.run_lock:
            if not self._running:
                job.sendWorkFail()
                return
            function_name = 'executor:execute'
            if self.zone:
                function_name += ':%s' % self.zone
            if job.name == (function_name):
                self.log.debug("Got %s job: %s" %
                               (function_name, job.unique))
                self.executeJob(job)
            elif job.name.startswith('executor:resume'):
                self.log.debug("Got resume job: %s" % job.unique)
                self.resumeJob(job)
            elif job.name.startswith('executor:stop'):
                self.log.debug("Got stop job: %s" % job.unique)
                self.stopJob(job)
            else:
                self.log.error("Unable to handle job %s" % job.name)
                job.sendWorkFail()

    def executeJob(self, job):
        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.incr(base_key + '.builds')
        self.job_workers[job.unique] = self._job_class(self, job)
        # Run manageLoad before starting the thread mostly for the
        # benefit of the unit tests to make the calculation of the
        # number of starting jobs more deterministic.
        self.manageLoad()
        self.job_workers[job.unique].run()

    def run_governor(self):
        while not self.governor_stop_event.wait(10):
            try:
                self.manageLoad()
            except Exception:
                self.log.exception("Exception in governor thread:")

    def manageLoad(self):
        ''' Apply some heuristics to decide whether or not we should
            be asking for more jobs '''
        with self.governor_lock:
            return self._manageLoad()

    def _manageLoad(self):

        if self.accepting_work:
            # Don't unregister if we don't have any active jobs.
            for sensor in self.sensors:
                ok, message = sensor.isOk()
                if not ok:
                    self.log.info(
                        "Unregistering due to {}".format(message))
                    self.unregister_work()
                    break
        else:
            reregister = True
            limits = []
            for sensor in self.sensors:
                ok, message = sensor.isOk()
                limits.append(message)
                if not ok:
                    reregister = False
                    break
            if reregister:
                self.log.info("Re-registering as job is within its limits "
                              "{}".format(", ".join(limits)))
                self.register_work()
        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            for sensor in self.sensors:
                sensor.reportStats(self.statsd, base_key)

    def finishJob(self, unique):
        del(self.job_workers[unique])

    def stopJobDiskFull(self, jobdir):
        unique = os.path.basename(jobdir)
        self.stopJobByUnique(unique, reason=AnsibleJob.RESULT_DISK_FULL)

    def resumeJob(self, job):
        try:
            args = json.loads(job.arguments)
            self.log.debug("Resume job with arguments: %s" % (args,))
            unique = args['uuid']
            self.resumeJobByUnique(unique)
        finally:
            job.sendWorkComplete()

    def stopJob(self, job):
        try:
            args = json.loads(job.arguments)
            self.log.debug("Stop job with arguments: %s" % (args,))
            unique = args['uuid']
            self.stopJobByUnique(unique)
        finally:
            job.sendWorkComplete()

    def resumeJobByUnique(self, unique):
        job_worker = self.job_workers.get(unique)
        if not job_worker:
            self.log.debug("Unable to find worker for job %s" % (unique,))
            return
        try:
            job_worker.resume()
        except Exception:
            self.log.exception("Exception sending resume command "
                               "to worker:")

    def stopJobByUnique(self, unique, reason=None):
        job_worker = self.job_workers.get(unique)
        if not job_worker:
            self.log.debug("Unable to find worker for job %s" % (unique,))
            return
        try:
            job_worker.stop(reason)
        except Exception:
            self.log.exception("Exception sending stop command "
                               "to worker:")

    def cat(self, job):
        args = json.loads(job.arguments)
        task = self.update(args['connection'], args['project'])
        task.wait()
        with self.merger_lock:
            files = self.merger.getFiles(args['connection'], args['project'],
                                         args['branch'], args['files'],
                                         args.get('dirs', []))
        result = dict(updated=True,
                      files=files)
        job.sendWorkComplete(json.dumps(result))

    def fileschanges(self, job):
        args = json.loads(job.arguments)
        task = self.update(args['connection'], args['project'])
        task.wait()
        with self.merger_lock:
            files = self.merger.getFilesChanges(
                args['connection'], args['project'],
                args['branch'],
                args['tosha'])
        result = dict(updated=True,
                      files=files)
        job.sendWorkComplete(json.dumps(result))

    def refstate(self, job):
        args = json.loads(job.arguments)
        with self.merger_lock:
            success, repo_state = self.merger.getRepoState(args['items'])
        result = dict(updated=success,
                      repo_state=repo_state)
        job.sendWorkComplete(json.dumps(result))

    def merge(self, job):
        args = json.loads(job.arguments)
        with self.merger_lock:
            ret = self.merger.mergeChanges(args['items'], args.get('files'),
                                           args.get('dirs', []),
                                           args.get('repo_state'))
        result = dict(merged=(ret is not None))
        if ret is None:
            result['commit'] = result['files'] = result['repo_state'] = None
        else:
            (result['commit'], result['files'], result['repo_state'],
             recent, orig_commit) = ret
        job.sendWorkComplete(json.dumps(result))
