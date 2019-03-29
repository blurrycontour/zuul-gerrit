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
import git
import json
import logging
import multiprocessing
import os
import socket
import subprocess
import threading
import time
import traceback
from concurrent.futures.process import ProcessPoolExecutor, BrokenProcessPool
import re

from zuul.lib.ansible import AnsibleManager
from zuul.lib.gearworker import ZuulGearWorker
from zuul.lib.result_data import get_warnings_from_result_data
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.statsd import get_statsd

import gear

import zuul.lib.repl
import zuul.merger.merger
import zuul.ansible.logconfig
from zuul.executor.common import AnsibleJob
from zuul.executor.common import AnsibleJobContextManager
from zuul.executor.common import DeduplicateQueue
from zuul.executor.common import DEFAULT_FINGER_PORT
from zuul.executor.common import DEFAULT_STREAM_PORT
from zuul.executor.common import ExecutorError
from zuul.executor.common import JobDir
from zuul.executor.common import MergerFetchFailure
from zuul.executor.common import MergerMergeFailure
from zuul.executor.common import SshAgent
from zuul.executor.common import UpdateTask
from zuul.executor.sensors.cpu import CPUSensor
from zuul.executor.sensors.hdd import HDDSensor
from zuul.executor.sensors.pause import PauseSensor
from zuul.executor.sensors.startingbuilds import StartingBuildsSensor
from zuul.executor.sensors.ram import RAMSensor
from zuul.lib import commandsocket
from zuul.lib import filecomments
from zuul.merger.server import BaseMergeServer, RepoLocks

COMMANDS = ['stop', 'pause', 'unpause', 'graceful', 'verbose',
            'unverbose', 'keep', 'nokeep', 'repl', 'norepl']


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
        # Remove any trailing slash to ensure dirname equality tests work
        cache_dir = cache_dir.rstrip('/')
        jobs_base = jobs_base.rstrip('/')
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
                    self.log.warning(
                        "{job} is using {size}MB (limit={limit})"
                        .format(size=size, job=dirname, limit=self.limit))
                    self.func(dirname)
                elif self.usage_func:
                    self.log.debug(
                        "{job} is using {size}MB (limit={limit})"
                        .format(size=size, job=dirname, limit=self.limit))
                    self.usage_func(dirname, size)
            du.wait()
            du.stdout.close()
            after = time.time()
            # Sleep half as long as that took, or 1s, whichever is longer
            delay_time = max((after - before) / 2, 1.0)
            self.stop_event.wait(delay_time)

    def start(self):
        if self.limit < 0:
            # No need to start if there is no limit.
            return
        self._running = True
        self.thread.start()

    def stop(self):
        if not self.running:
            return
        self._running = False
        self.stop_event.set()
        self.thread.join()

    @property
    def running(self):
        return self._running


class GearmanAnsibleContextManager(AnsibleJobContextManager):
    """An object to manage the threaded gearman ansible job used by the
    executor service.

    The GearmanAnsibleContextManager is responsible for creating and managing
    an AnsibleJob in a thread as well as sending the result data back to the
    gearman. The constructor is also responsible for interfacing the
    executor service configurations with the base AnsibleJob requirements.

    The caller must invoke the run procedure to execute a job.
    """
    _job_class = AnsibleJob

    def __init__(self, executor_server, gearman_job):
        super(GearmanAnsibleContextManager, self).__init__()

        extra_paths = {}
        for context in ("trusted", "untrusted"):
            extra_paths[context] = {}
            for type_path in ("ro", "rw"):
                conf = get_default(
                    executor_server.config,
                    'executor',
                    '%s_%s_paths' % (context, type_path))
                extra_paths[
                    context][type_path] = conf.split(":") if conf else []

        self.executor_server = executor_server
        self.gearman_job = gearman_job
        self.gearman_arguments = json.loads(self.gearman_job.arguments)
        self.unique = self.gearman_job.unique

        # Logger name left for backwards compatability and its shortness
        logger = logging.getLogger("zuul.AnsibleJob")
        self.zuul_event_id = self.gearman_arguments.get('zuul_event_id')
        self.log = get_annotated_logger(
            logger, self.zuul_event_id, build=self.unique)

        self.time_starting_build = None
        self._resume_event = threading.Event()
        self.thread = None
        self.private_key_file = get_default(self.executor_server.config,
                                            'executor', 'private_key_file',
                                            '~/.ssh/id_rsa')

        self.ssh_agent = SshAgent(zuul_event_id=self.zuul_event_id,
                                  build=self.unique)
        self.port_forwards = []

        executor_variables_file = None
        if self.executor_server.config.has_option('executor', 'variables'):
            executor_variables_file = self.executor_server.config.get(
                'executor', 'variables')

        ara_callbacks = \
            self.executor_server.ansible_manager.getAraCallbackPlugin(
                self.gearman_arguments.get('ansible_version'))
        ansible_callbacks = self.executor_server.ansible_callbacks
        plugin_dir = self.executor_server.ansible_manager.getAnsiblePluginDir(
            self.gearman_arguments.get('ansible_version'))

        self.ansible_job = self._job_class(
            self.unique,
            self.zuul_event_id,
            context_manager=self,
            getMerger=executor_server._getMerger,
            process_worker=executor_server.process_worker,
            merge_root=executor_server.merge_root,
            connections=executor_server.connections,
            ansible_manager=executor_server.ansible_manager,
            execution_wrapper=executor_server.execution_wrapper,
            logger=self.log,
            verbose=executor_server.verbose,
            setup_timeout=executor_server.setup_timeout,
            executor_hostname=executor_server.hostname,
            default_username=executor_server.default_username,
            statsd=executor_server.statsd,
            ansible_plugin_dir=plugin_dir,
            ansible_ara_callbacks=ara_callbacks,
            ansible_callbacks=ansible_callbacks,
            executor_variables_file=executor_variables_file,
            executor_extra_paths=extra_paths
        )

        self.ansible_job.setWinrmOptions(
            key_file=get_default(self.executor_server.config,
                                 'executor', 'winrm_cert_key_file',
                                 '~/.winrm/winrm_client_cert.key'),
            pem_file=get_default(self.executor_server.config,
                                 'executor', 'winrm_cert_pem_file',
                                 '~/.winrm/winrm_client_cert.pem'),
            operation_timeout=get_default(self.executor_server.config,
                                          'executor',
                                          'winrm_operation_timeout_sec'),
            read_timeout=get_default(self.executor_server.config,
                                     'executor',
                                     'winrm_read_timeout_sec')
        )

    def run(self):
        self.running = True
        self.thread = threading.Thread(
            target=self.execute, name='build-%s' % self.gearman_job.unique)
        self.thread.start()

    def stop(self, reason=None):
        self.aborted = True
        self.aborted_reason = reason

        # if paused we need to resume the job so it can be stopped
        self.resume()
        self.ansible_job.abortRunningProc()

    def pause(self):
        self.log.info(
            "Pausing job %s for ref %s (change %s)" % (
                self.gearman_arguments['zuul']['job'],
                self.gearman_arguments['zuul']['ref'],
                self.gearman_arguments['zuul']['change_url']))
        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write(
                "{now} |\n"
                "{now} | Job paused\n".format(now=datetime.datetime.now()))

        self.paused = True
        self.ansible_job.pause()

        data = {
            'paused': self.paused,
            'data': self.ansible_job.getResultData(),
        }
        self.gearman_job.sendWorkData(json.dumps(data))
        self._resume_event.wait()

    def resume(self):
        if not self.paused:
            return

        self.log.info(
            "Resuming job %s for ref %s (change %s)" % (
                self.gearman_arguments['zuul']['job'],
                self.gearman_arguments['zuul']['ref'],
                self.gearman_arguments['zuul']['change_url']))
        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write(
                "{now} | Job resumed\n"
                "{now} |\n".format(now=datetime.datetime.now()))

        self.paused = False
        self.ansible_job.resume()
        self._resume_event.set()

    def wait(self):
        if self.thread:
            self.thread.join()

    def execute(self):
        self.jobdir = None
        try:
            self.time_starting_build = time.monotonic()

            # report that job has been taken
            self.gearman_job.sendWorkData(json.dumps(self._base_job_data()))

            self.ssh_agent.start()
            self.ssh_agent.add(self.private_key_file)
            for key in self.gearman_arguments.get('ssh_keys', []):
                self.ssh_agent.addData(key['name'], key['key'])
            self.jobdir = JobDir(self.executor_server.jobdir_root,
                                 self.executor_server.keep_jobdir,
                                 str(self.gearman_job.unique))
            self.ansible_job.setJobDir(self.jobdir)
            self.ansible_job.setExtraEnvVars(self.ssh_agent.env)
            self._execute()
        except BrokenProcessPool:
            # The process pool got broken, re-initialize it and send
            # ABORTED so we re-try the job.
            self.log.exception('Process pool got broken')
            self.executor_server.resetProcessPool()
            self.send_aborted()
        except ExecutorError as e:
            result_data = json.dumps(dict(result='ERROR',
                                          error_detail=e.args[0]))
            self.log.debug("Sending result: %s" % (result_data,))
            self.gearman_job.sendWorkComplete(result_data)
        except Exception:
            self.log.exception("Exception while executing job")
            self.gearman_job.sendWorkException(traceback.format_exc())
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
            for fwd in self.port_forwards:
                try:
                    fwd.stop()
                except Exception:
                    self.log.exception("Error stopping port forward:")
            try:
                self.executor_server.finishJob(self.gearman_job.unique)
            except Exception:
                self.log.exception("Error finalizing job thread:")
            self.log.info("Job execution took: %.3f seconds" % (
                time.monotonic() - self.time_starting_build))

    def _base_job_data(self):
        return {
            # TODO(mordred) worker_name is needed as a unique name for the
            # client to use for cancelling jobs on an executor. It's
            # defaulting to the hostname for now, but in the future we
            # should allow setting a per-executor override so that one can
            # run more than one executor on a host.
            'worker_name': self.executor_server.hostname,
            'worker_hostname': self.executor_server.hostname,
            'worker_log_port': self.executor_server.log_streaming_port,
        }

    def send_aborted(self):
        result = dict(result='ABORTED')
        self.gearman_job.sendWorkComplete(json.dumps(result))

    def _execute(self):
        args = self.gearman_arguments
        self.log.info(
            "Beginning job %s for ref %s (change %s)" % (
                args['zuul']['job'],
                args['zuul']['ref'],
                args['zuul']['change_url']))
        self.log.debug("Job root: %s" % (self.jobdir.root,))

        try:
            item_commit, merger = self.ansible_job.prepareRepositories(
                self.executor_server.update, args)
        except MergerFetchFailure:
            # Return ABORTED so that we'll try again. At this point all of
            # the refs we're trying to merge should be valid refs. If we
            # can't fetch them, it should resolve itself.
            result = dict(result='ABORTED')
            self.gearman_job.sendWorkComplete(json.dumps(result))
            return
        except MergerMergeFailure:
            # Merge conflict
            result = dict(result='MERGER_FAILURE')
            self.gearman_job.sendWorkComplete(json.dumps(result))
            return
        if item_commit is False:
            # There was a merge conflict and we have already sent
            # a work complete result, don't run any jobs
            return

        # Early abort if abort requested
        if self.aborted:
            self.send_aborted()
            return

        # This prepares each playbook and the roles needed for each.
        self.ansible_job.preparePlaybooks(args)

        self.ansible_job.prepareAnsibleFiles(args)
        self.ansible_job.writeLoggingConfig()

        # Early abort if abort requested
        if self.aborted:
            self.send_aborted()
            return

        data = self._base_job_data()
        if self.executor_server.log_streaming_port != DEFAULT_FINGER_PORT:
            data['url'] = "finger://{hostname}:{port}/{uuid}".format(
                hostname=self.executor_server.hostname,
                port=self.executor_server.log_streaming_port,
                uuid=self.gearman_job.unique)
        else:
            data['url'] = 'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=self.gearman_job.unique)

        self.gearman_job.sendWorkData(json.dumps(data))
        self.gearman_job.sendWorkStatus(0, 100)

        result = self.ansible_job.runPlaybooks(args, self.time_starting_build)
        success = result == 'SUCCESS'

        self.ansible_job.runCleanupPlaybooks(success)

        # Stop the persistent SSH connections.
        setup_status, setup_code = self.ansible_job.runAnsibleCleanup(
            self.jobdir.setup_playbook)

        if self.aborted_reason == AnsibleJob.RESULT_DISK_FULL:
            result = 'DISK_FULL'
        data = self.ansible_job.getResultData()
        warnings = []
        self.mapLines(merger, args, data, item_commit, warnings)
        warnings.extend(get_warnings_from_result_data(data, logger=self.log))
        result_data = json.dumps(dict(result=result,
                                      warnings=warnings,
                                      data=data))
        self.log.debug("Sending result: %s" % (result_data,))
        self.gearman_job.sendWorkComplete(result_data)

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


class ExecutorMergeWorker(gear.TextWorker):
    def __init__(self, executor_server, *args, **kw):
        self.zuul_executor_server = executor_server
        super(ExecutorMergeWorker, self).__init__(*args, **kw)

    def handleNoop(self, packet):
        # Wait until the update queue is empty before responding
        while self.zuul_executor_server.update_queue.qsize():
            time.sleep(1)

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


class ExecutorServer(BaseMergeServer):
    log = logging.getLogger("zuul.ExecutorServer")
    _ansible_manager_class = AnsibleManager
    _job_context_class = GearmanAnsibleContextManager
    _repo_locks_class = RepoLocks

    def __init__(
        self,
        config,
        connections=None,
        jobdir_root=None,
        keep_jobdir=False,
        log_streaming_port=DEFAULT_FINGER_PORT,
        log_console_port=DEFAULT_STREAM_PORT,
    ):
        super().__init__(config, 'executor', connections)

        self.keep_jobdir = keep_jobdir
        self.jobdir_root = jobdir_root
        # TODOv3(mordred): make the executor name more unique --
        # perhaps hostname+pid.
        self.hostname = get_default(self.config, 'executor', 'hostname',
                                    socket.getfqdn())
        self.log_streaming_port = log_streaming_port
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
            repl=self.start_repl,
            norepl=self.stop_repl,
        )
        self.log_console_port = log_console_port
        self.repl = None

        statsd_extra_keys = {'hostname': self.hostname}
        self.statsd = get_statsd(config, statsd_extra_keys)
        self.default_username = get_default(self.config, 'executor',
                                            'default_username', 'zuul')
        self.disk_limit_per_job = int(get_default(self.config, 'executor',
                                                  'disk_limit_per_job', 250))
        self.setup_timeout = int(get_default(self.config, 'executor',
                                             'ansible_setup_timeout', 60))
        self.zone = get_default(self.config, 'executor', 'zone')
        self.allow_unzoned = get_default(self.config, 'executor',
                                         'allow_unzoned', False)

        self.ansible_callbacks = {}
        for section_name in self.config.sections():
            cb_match = re.match(r'^ansible_callback ([\'\"]?)(.*)(\1)$',
                                section_name, re.I)
            if not cb_match:
                continue
            cb_name = cb_match.group(2)
            self.ansible_callbacks[cb_name] = dict(
                self.config.items(section_name)
            )

        # TODO(tobiash): Take cgroups into account
        self.update_workers = multiprocessing.cpu_count()
        self.update_threads = []
        # If the execution driver ever becomes configurable again,
        # this is where it would happen.
        execution_wrapper_name = 'bubblewrap'
        self.accepting_work = False
        self.execution_wrapper = connections.drivers[execution_wrapper_name]

        self.update_queue = DeduplicateQueue()

        command_socket = get_default(
            self.config, 'executor', 'command_socket',
            '/var/lib/zuul/executor.socket')
        self.command_socket = commandsocket.CommandSocket(command_socket)

        state_dir = get_default(self.config, 'executor', 'state_dir',
                                '/var/lib/zuul', expand_user=True)

        # If keep is not set, ensure the job dir is empty on startup,
        # in case we were uncleanly shut down.
        if not self.keep_jobdir:
            for fn in os.listdir(self.jobdir_root):
                fn = os.path.join(self.jobdir_root, fn)
                if not os.path.isdir(fn):
                    continue
                self.log.info("Deleting stale jobdir %s", fn)
                # We use rm here instead of shutil because of
                # https://bugs.python.org/issue22040
                jobdir = os.path.join(self.jobdir_root, fn)
                # First we need to ensure all directories are
                # writable to avoid permission denied error
                subprocess.Popen([
                    "find", jobdir,
                    # Filter non writable perms
                    "-type", "d", "!", "-perm", "/u+w",
                    # Replace by writable perms
                    "-exec", "chmod", "0700", "{}", "+"]).wait()
                if subprocess.Popen(["rm", "-Rf", jobdir]).wait():
                    raise RuntimeError("Couldn't delete: " + jobdir)

        self.job_workers = {}
        self.disk_accountant = DiskAccountant(self.jobdir_root,
                                              self.disk_limit_per_job,
                                              self.stopJobDiskFull,
                                              self.merge_root)

        self.pause_sensor = PauseSensor(get_default(self.config, 'executor',
                                                    'paused_on_start', False))
        self.log.info("Starting executor (hostname: %s) in %spaused mode" % (
            self.hostname, "" if self.pause_sensor.pause else "un"))
        cpu_sensor = CPUSensor(config)
        self.sensors = [
            cpu_sensor,
            HDDSensor(config),
            self.pause_sensor,
            RAMSensor(config),
            StartingBuildsSensor(self, cpu_sensor.max_load_avg, config)
        ]

        manage_ansible = get_default(
            self.config, 'executor', 'manage_ansible', True)
        ansible_dir = os.path.join(state_dir, 'ansible')
        ansible_install_root = get_default(
            self.config, 'executor', 'ansible_root', None)
        if not ansible_install_root:
            # NOTE: Even though we set this value the zuul installation
            # adjacent virtualenv location is still checked by the ansible
            # manager. ansible_install_root's value is only used if those
            # default locations do not have venvs preinstalled.
            ansible_install_root = os.path.join(state_dir, 'ansible-bin')
        self.ansible_manager = self._ansible_manager_class(
            ansible_dir, runtime_install_root=ansible_install_root)
        if not self.ansible_manager.validate():
            if not manage_ansible:
                raise Exception('Error while validating ansible '
                                'installations. Please run '
                                'zuul-manage-ansible to install all supported '
                                'ansible versions.')
            else:
                self.ansible_manager.install()
        self.ansible_manager.copyAnsibleFiles()

        self.process_merge_jobs = get_default(self.config, 'executor',
                                              'merge_jobs', True)

        self.executor_jobs = {
            "executor:resume:%s" % self.hostname: self.resumeJob,
            "executor:stop:%s" % self.hostname: self.stopJob,
        }
        for function_name in self._getExecuteFunctionNames():
            self.executor_jobs[function_name] = self.executeJob
        for function_name in self._getOnlineFunctionNames():
            self.executor_jobs[function_name] = self.noop

        self.executor_gearworker = ZuulGearWorker(
            'Zuul Executor Server',
            'zuul.ExecutorServer.ExecuteWorker',
            'executor',
            self.config,
            self.executor_jobs,
            worker_class=ExecutorExecuteWorker,
            worker_args=[self])

        # Used to offload expensive operations to different processes
        self.process_worker = None

    def _getFunctionSuffixes(self):
        suffixes = []
        if self.zone:
            suffixes.append(':' + self.zone)
            if self.allow_unzoned:
                suffixes.append('')
        else:
            suffixes.append('')
        return suffixes

    def _getExecuteFunctionNames(self):
        base_name = 'executor:execute'
        return [base_name + suffix for suffix in self._getFunctionSuffixes()]

    def _getOnlineFunctionNames(self):
        base_name = 'executor:online'
        return [base_name + suffix for suffix in self._getFunctionSuffixes()]

    def _repoLock(self, connection_name, project_name):
        return self.repo_locks.getRepoLock(connection_name, project_name)

    def noop(self, job):
        """A noop gearman job so we can register for statistics."""
        job.sendWorkComplete()

    def start(self):
        # Start merger worker only if we process merge jobs
        if self.process_merge_jobs:
            super().start()

        self._running = True
        self._command_running = True

        try:
            multiprocessing.set_start_method('spawn')
        except RuntimeError:
            # Note: During tests this can be called multiple times which
            # results in a runtime error. This is ok here as we've set this
            # already correctly.
            self.log.warning('Multiprocessing context has already been set')
        self.process_worker = ProcessPoolExecutor()

        self.executor_gearworker.start()

        self.log.debug("Starting command processor")
        self.command_socket.start()
        self.command_thread = threading.Thread(target=self.runCommand,
                                               name='command')
        self.command_thread.daemon = True
        self.command_thread.start()

        self.log.debug("Starting %s update workers" % self.update_workers)
        for i in range(self.update_workers):
            update_thread = threading.Thread(target=self._updateLoop,
                                             name='update')
            update_thread.daemon = True
            update_thread.start()
            self.update_threads.append(update_thread)

        self.governor_stop_event = threading.Event()
        self.governor_thread = threading.Thread(target=self.run_governor,
                                                name='governor')
        self.governor_thread.daemon = True
        self.governor_thread.start()
        self.disk_accountant.start()

    def register_work(self):
        if self._running:
            self.accepting_work = True
            for function in self._getExecuteFunctionNames():
                self.executor_gearworker.gearman.registerFunction(function)
            # TODO(jeblair): Update geard to send a noop after
            # registering for a job which is in the queue, then remove
            # this API violation.
            self.executor_gearworker.gearman._sendGrabJobUniq()

    def unregister_work(self):
        self.accepting_work = False
        for function in self._getExecuteFunctionNames():
            self.executor_gearworker.gearman.unRegisterFunction(function)

    def stop(self):
        self.log.debug("Stopping")
        # Use the BaseMergeServer's stop method to disconnect from ZooKeeper.
        super().stop()
        self.connections.stop()
        self.disk_accountant.stop()
        # The governor can change function registration, so make sure
        # it has stopped.
        self.governor_stop_event.set()
        self.governor_thread.join()
        # Stop accepting new jobs
        if self.merger_gearworker is not None:
            self.merger_gearworker.gearman.setFunctions([])
        self.executor_gearworker.gearman.setFunctions([])
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
        for _ in self.update_threads:
            self.update_queue.put(None)

        self.command_socket.stop()

        # All job results should have been sent by now, shutdown the
        # gearman workers.
        self.executor_gearworker.stop()

        if self.process_worker is not None:
            self.process_worker.shutdown()

        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.gauge(base_key + '.load_average', 0)
            self.statsd.gauge(base_key + '.pct_used_ram', 0)
            self.statsd.gauge(base_key + '.running_builds', 0)

        self.stop_repl()
        self.log.debug("Stopped")

    def join(self):
        self.governor_thread.join()
        for update_thread in self.update_threads:
            update_thread.join()
        if self.process_merge_jobs:
            super().join()
        self.executor_gearworker.join()
        self.command_thread.join()

    def pause(self):
        self.log.debug('Pausing')
        self.pause_sensor.pause = True
        if self.process_merge_jobs:
            super().pause()

    def unpause(self):
        self.log.debug('Resuming')
        self.pause_sensor.pause = False
        if self.process_merge_jobs:
            super().unpause()

    def graceful(self):
        # This pauses the executor end shuts it down when there is no running
        # build left anymore
        self.log.info('Stopping graceful')
        self.pause()
        while self.job_workers:
            self.log.debug('Waiting for %s jobs to end', len(self.job_workers))
            time.sleep(30)
        try:
            self.stop()
        except Exception:
            self.log.exception('Error while stopping')

    def verboseOn(self):
        self.verbose = True

    def verboseOff(self):
        self.verbose = False

    def keep(self):
        self.keep_jobdir = True

    def nokeep(self):
        self.keep_jobdir = False

    def start_repl(self):
        if self.repl:
            return
        self.repl = zuul.lib.repl.REPLServer(self)
        self.repl.start()

    def stop_repl(self):
        if not self.repl:
            # not running
            return
        self.repl.stop()
        self.repl = None

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

    def resetProcessPool(self):
        """
        This is called in order to re-initialize a broken process pool if it
        got broken e.g. by an oom killed child process
        """
        if self.process_worker:
            try:
                self.process_worker.shutdown()
            except Exception:
                self.log.exception('Failed to shutdown broken process worker')
            self.process_worker = ProcessPoolExecutor()

    def _innerUpdateLoop(self):
        # Inside of a loop that keeps the main repositories up to date
        task = self.update_queue.get()
        if task is None:
            # We are asked to stop
            raise StopException()
        log = get_annotated_logger(
            self.log, task.zuul_event_id, build=task.build)
        try:
            lock = self.repo_locks.getRepoLock(
                task.connection_name, task.project_name)
            with lock:
                log.info("Updating repo %s/%s",
                         task.connection_name, task.project_name)
                self.merger.updateRepo(
                    task.connection_name, task.project_name,
                    repo_state=task.repo_state,
                    zuul_event_id=task.zuul_event_id, build=task.build,
                    process_worker=self.process_worker)
                repo = self.merger.getRepo(
                    task.connection_name, task.project_name)
                source = self.connections.getSource(task.connection_name)
                project = source.getProject(task.project_name)
                task.canonical_name = project.canonical_name
                task.branches = repo.getBranches()
                task.refs = [r.name for r in repo.getRefs()]
                log.debug("Finished updating repo %s/%s",
                          task.connection_name, task.project_name)
                task.success = True
        except BrokenProcessPool:
            # The process pool got broken. Reset it to unbreak it for further
            # requests.
            log.exception('Process pool got broken')
            self.resetProcessPool()
        except Exception:
            log.exception('Got exception while updating repo %s/%s',
                          task.connection_name, task.project_name)
        finally:
            task.setComplete()

    def update(self, connection_name, project_name, repo_state=None,
               zuul_event_id=None, build=None):
        # Update a repository in the main merger

        state = None
        if repo_state:
            state = repo_state.get(connection_name, {}).get(project_name)

        task = UpdateTask(connection_name, project_name, repo_state=state,
                          zuul_event_id=zuul_event_id, build=build)
        task = self.update_queue.put(task)
        return task

    def _update(self, connection_name, project_name, zuul_event_id=None):
        """
        The executor overrides _update so it can do the update asynchronously.
        """
        log = get_annotated_logger(self.log, zuul_event_id)
        task = self.update(connection_name, project_name,
                           zuul_event_id=zuul_event_id)
        task.wait()
        if not task.success:
            msg = "Update of '{}' failed".format(project_name)
            log.error(msg)
            raise Exception(msg)

    def executeJob(self, job):
        args = json.loads(job.arguments)
        zuul_event_id = args.get('zuul_event_id')
        log = get_annotated_logger(self.log, zuul_event_id)
        log.debug("Got %s job: %s", job.name, job.unique)
        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.incr(base_key + '.builds')
        self.job_workers[job.unique] = self._job_context_class(self, job)
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
        self.stopJobByUnique(
            unique, reason=self._job_context_class._job_class.RESULT_DISK_FULL)

    def resumeJob(self, job):
        try:
            args = json.loads(job.arguments)
            zuul_event_id = args.get('zuul_event_id')
            log = get_annotated_logger(self.log, zuul_event_id)
            log.debug("Resume job with arguments: %s", args)
            unique = args['uuid']
            self.resumeJobByUnique(unique, zuul_event_id=zuul_event_id)
        finally:
            job.sendWorkComplete()

    def stopJob(self, job):
        try:
            args = json.loads(job.arguments)
            zuul_event_id = args.get('zuul_event_id')
            log = get_annotated_logger(self.log, zuul_event_id)
            log.debug("Stop job with arguments: %s", args)
            unique = args['uuid']
            self.stopJobByUnique(unique, zuul_event_id=zuul_event_id)
        finally:
            job.sendWorkComplete()

    def resumeJobByUnique(self, unique, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        job_worker = self.job_workers.get(unique)
        if not job_worker:
            log.debug("Unable to find worker for job %s", unique)
            return
        try:
            job_worker.resume()
        except Exception:
            log.exception("Exception sending resume command to worker:")

    def stopJobByUnique(self, unique, reason=None, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        job_worker = self.job_workers.get(unique)
        if not job_worker:
            log.debug("Unable to find worker for job %s", unique)
            return
        try:
            job_worker.stop(reason)
        except Exception:
            log.exception("Exception sending stop command to worker:")
