# Copyright 2014 OpenStack Foundation
# Copyright 2021 Acme Gating, LLC
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
import multiprocessing
import os
import re
import socket
import subprocess
import threading
import time
import traceback
from concurrent.futures.process import ProcessPoolExecutor, BrokenProcessPool

from kazoo.exceptions import NoNodeError

from zuul.lib.ansible import AnsibleManager
from zuul.lib.result_data import get_warnings_from_result_data
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.statsd import get_statsd
from zuul.lib.keystorage import KeyStorage

import zuul.lib.repl
import zuul.merger.merger
import zuul.ansible.logconfig
from zuul.executor.common import AnsibleJob
from zuul.executor.common import DeduplicateQueue
from zuul.executor.common import DEFAULT_FINGER_PORT
from zuul.executor.common import DEFAULT_STREAM_PORT
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
from zuul.merger.server import BaseMergeServer, RepoLocks
from zuul.model import (
    BuildCompletedEvent,
    BuildPausedEvent,
    BuildRequest,
    BuildStartedEvent,
    BuildStatusEvent,
    NodeSet,
)
import zuul.model
from zuul.nodepool import Nodepool
from zuul.version import get_version_string
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.components import ExecutorComponent
from zuul.zk.exceptions import JobRequestNotFound
from zuul.zk.executor import ExecutorApi
from zuul.zk.job_request_queue import JobRequestEvent
from zuul.zk.system import ZuulSystem

COMMANDS = ['stop', 'pause', 'unpause', 'graceful', 'verbose',
            'unverbose', 'keep', 'nokeep', 'repl', 'norepl']


class NodeRequestError(Exception):
    pass


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


class AnsibleJobZK(AnsibleJob):
    """An object to manage threaded job used by the executor service.
    The AnsibleJobZK is responsible for creating and managing
    an AnsibleJob thread as well as sending the result data back to the
    ZooKeeper. The constructor is also responsible for interfacing the
    executor service configurations with the base AnsibleJob requirements.
    The caller must invoke the run procedure to execute a job.
    NOTE(jhesketh): To reduce review complexity, at the moment this class still
                    inherits from AnsibleJob. This change should mostly be a
                    copy out of the class that was here into the common
                    library. In subsuqent changes we will rework this to
                    consume AnsibleJob rather than extend it.
    """
    def __init__(self, executor_server, build_request, arguments):
        logger = logging.getLogger("zuul.AnsibleJob")
        self.arguments = arguments
        self.zuul_event_id = self.arguments["zuul_event_id"]
        # Record ansible version being used for the cleanup phase
        self.ansible_version = self.arguments.get('ansible_version')
        # TODO(corvus): Remove default setting after 4.3.0; this is to handle
        # scheduler/executor version skew.
        self.scheme = self.arguments.get('workspace_scheme',
                                         zuul.model.SCHEME_GOLANG)
        self.log = get_annotated_logger(
            logger, self.zuul_event_id, build=build_request.uuid
        )
        self.executor_server = executor_server
        self.build_request = build_request
        self.nodeset = None
        self.node_request = None
        self.jobdir = None
        self.proc = None
        self.proc_lock = threading.Lock()
        self.running = False
        self.started = False  # Whether playbooks have started running
        self.time_starting_build = None
        self.paused = False
        self.aborted = False
        self.aborted_reason = None
        self.cleanup_started = False
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
        self.ssh_agent = SshAgent(zuul_event_id=self.zuul_event_id,
                                  build=self.build_request.uuid)
        self.port_forwards = []
        self.executor_variables_file = None

        self.cpu_times = {'user': 0, 'system': 0,
                          'children_user': 0, 'children_system': 0}

        if self.executor_server.config.has_option('executor', 'variables'):
            self.executor_variables_file = self.executor_server.config.get(
                'executor', 'variables')

        plugin_dir = self.executor_server.ansible_manager.getAnsiblePluginDir(
            self.arguments.get('ansible_version'))
        self.ara_callbacks = \
            self.executor_server.ansible_manager.getAraCallbackPlugin(
                self.arguments.get('ansible_version'))
        self.library_dir = os.path.join(plugin_dir, 'library')
        self.action_dir = os.path.join(plugin_dir, 'action')
        self.action_dir_general = os.path.join(plugin_dir, 'actiongeneral')
        self.action_dir_trusted = os.path.join(plugin_dir, 'actiontrusted')
        self.callback_dir = os.path.join(plugin_dir, 'callback')
        self.lookup_dir = os.path.join(plugin_dir, 'lookup')
        self.filter_dir = os.path.join(plugin_dir, 'filter')
        self.ansible_callbacks = self.executor_server.ansible_callbacks
        # The result of getHostList
        self.host_list = None
        # The supplied job/host/group/extra vars, squashed.  Indexed
        # by hostname.
        self.original_hostvars = {}
        # The same, but frozen
        self.frozen_hostvars = {}
        # The zuul.* vars
        self.zuul_vars = {}

    def run(self):
        self.running = True
        self.thread = threading.Thread(target=self.execute,
                                       name=f"build-{self.build_request.uuid}")
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

        result_data, secret_result_data = self.getResultData()
        data = {'paused': self.paused,
                'data': result_data,
                'secret_data': secret_result_data}
        self.executor_server.pauseBuild(self.build_request, data)
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
        self.executor_server.resumeBuild(self.build_request)
        self._resume_event.set()

    def wait(self):
        if self.thread:
            self.thread.join()

    def execute(self):
        try:
            self.time_starting_build = time.monotonic()

            # report that job has been taken
            self.executor_server.startBuild(
                self.build_request, self._base_job_data()
            )

            self.setNodeInfo()

            self.ssh_agent.start()
            self.ssh_agent.add(self.private_key_file)
            for key in self.arguments.get('ssh_keys', []):
                private_ssh_key, public_ssh_key = \
                    self.executor_server.keystore.getProjectSSHKeys(
                        key['connection_name'],
                        key['project_name'])
                name = '%s project key' % (key['project_name'])
                self.ssh_agent.addData(name, private_ssh_key)
            self.jobdir = JobDir(self.executor_server.jobdir_root,
                                 self.executor_server.keep_jobdir,
                                 str(self.build_request.uuid))
            self.lockNodes()
            self._execute()
        except NodeRequestError:
            result_data = dict(
                result="NODE_FAILURE", exception=traceback.format_exc()
            )
            self.executor_server.completeBuild(self.build_request, result_data)
        except BrokenProcessPool:
            # The process pool got broken, re-initialize it and send
            # ABORTED so we re-try the job.
            self.log.exception('Process pool got broken')
            self.executor_server.resetProcessPool()
            self._send_aborted()
        except ExecutorError as e:
            result_data = dict(result='ERROR', error_detail=e.args[0])
            self.log.debug("Sending result: %s", result_data)
            self.executor_server.completeBuild(self.build_request, result_data)
        except Exception:
            self.log.exception("Exception while executing job")
            data = {"exception": traceback.format_exc()}
            self.executor_server.completeBuild(self.build_request, data)
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

            # Make sure we return the nodes to nodepool in any case.
            self.unlockNodes()
            try:
                self.executor_server.finishJob(self.build_request.uuid)
            except Exception:
                self.log.exception("Error finalizing job thread:")
            self.log.info("Job execution took: %.3f seconds",
                          self.end_time - self.time_starting_build)

    def setNodeInfo(self):
        try:
            # This shouldn't fail - but theoretically it could. So we handle
            # it similar to a NodeRequestError.
            self.nodeset = NodeSet.fromDict(self.arguments["nodeset"])
        except KeyError:
            self.log.error("Unable to deserialize nodeset")
            raise NodeRequestError

        # Look up the NodeRequest with the provided ID from ZooKeeper. If
        # no ID is provided, this most probably means that the NodeRequest
        # wasn't submitted to ZooKeeper.
        node_request_id = self.arguments.get("noderequest_id")
        if node_request_id:
            zk_nodepool = self.executor_server.nodepool.zk_nodepool
            self.node_request = zk_nodepool.getNodeRequest(
                self.arguments["noderequest_id"])

            if self.node_request is None:
                self.log.error(
                    "Unable to retrieve NodeReqest %s from ZooKeeper",
                    node_request_id,
                )
                raise NodeRequestError

    def lockNodes(self):
        # If the node_request is not set, this probably means that the
        # NodeRequest didn't contain any nodes and thus was never submitted
        # to ZooKeeper. In that case we don't have anything to lock before
        # executing the build.
        if self.node_request:
            self.log.debug("Locking nodeset")
            try:
                self.executor_server.nodepool.acceptNodes(
                    self.node_request, self.nodeset)
            except Exception:
                self.log.exception(
                    "Error locking nodeset %s", self.nodeset
                )
                raise NodeRequestError

    def unlockNodes(self):
        if self.node_request:
            tenant_name = self.arguments["zuul"]["tenant"]
            project_name = self.arguments["zuul"]["project"]["canonical_name"]
            duration = self.end_time - self.time_starting_build
            try:
                self.executor_server.nodepool.returnNodeSet(
                    self.nodeset,
                    self.build_request,
                    tenant_name,
                    project_name,
                    duration,
                    zuul_event_id=self.zuul_event_id,
                )
            except Exception:
                self.log.exception(
                    "Unable to return nodeset %s", self.nodeset
                )

    def _base_job_data(self):
        data = {
            # TODO(mordred) worker_name is needed as a unique name for the
            # client to use for cancelling jobs on an executor. It's
            # defaulting to the hostname for now, but in the future we
            # should allow setting a per-executor override so that one can
            # run more than one executor on a host.
            'worker_name': self.executor_server.hostname,
            'worker_hostname': self.executor_server.hostname,
            'worker_log_port': self.executor_server.log_streaming_port,
        }
        if self.executor_server.zone:
            data['worker_zone'] = self.executor_server.zone
        return data

    def _send_aborted(self):
        result = dict(result='ABORTED')
        self.executor_server.completeBuild(self.build_request, result)

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
        repo_state = args['repo_state']

        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write("{now} | Updating repositories\n".format(
                now=datetime.datetime.now()
            ))
        # Make sure all projects used by the job are updated...
        for project in args['projects']:
            self.log.debug("Updating project %s" % (project,))
            tasks.append(self.executor_server.update(
                project['connection'], project['name'],
                repo_state=repo_state,
                zuul_event_id=self.zuul_event_id,
                build=self.build_request.uuid))
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
                tasks.append(self.executor_server.update(
                    *key, repo_state=repo_state,
                    zuul_event_id=self.zuul_event_id,
                    build=self.build_request.uuid))
                projects.add(key)

        for task in tasks:
            task.wait()

            if not task.success:
                # On transient error retry the job
                if hasattr(task, 'transient_error') and task.transient_error:
                    result = dict(
                        result=None,
                        error_detail=f'Failed to update project '
                                     f'{task.project_name}')
                    self.job.sendWorkComplete(
                        json.dumps(result, sort_keys=True))
                    return

                raise ExecutorError(
                    'Failed to update project %s' % task.project_name)

            # Take refs and branches from repo state
            project_repo_state = \
                repo_state[task.connection_name][task.project_name]
            # All branch names
            branches = [
                ref[11:]  # strip refs/heads/
                for ref in project_repo_state
                if ref.startswith('refs/heads/')
            ]
            # All refs without refs/*/ prefix
            refs = []
            for ref in project_repo_state:
                r = '/'.join(ref.split('/')[2:])
                if r:
                    refs.append(r)
            self.project_info[task.canonical_name] = {
                'refs': refs,
                'branches': branches,
            }

        # Early abort if abort requested
        if self.aborted:
            self._send_aborted()
            return
        self.log.debug("Git updates complete")

        with open(self.jobdir.job_output_file, 'a') as job_output:
            job_output.write("{now} | Preparing job workspace\n".format(
                now=datetime.datetime.now()
            ))
        merger = self.executor_server._getMerger(
            self.jobdir.src_root,
            self.executor_server.merge_root,
            logger=self.log,
            scheme=self.scheme)
        repos = {}
        for project in args['projects']:
            self.log.debug("Cloning %s/%s" % (project['connection'],
                                              project['name'],))
            repo = merger.getRepo(
                project['connection'],
                project['name'],
                process_worker=self.executor_server.process_worker)
            repos[project['canonical_name']] = repo

        # The commit ID of the original item (before merging).  Used
        # later for line mapping.
        item_commit = None
        # The set of repos which have had their state restored
        restored_repos = set()

        merge_items = [i for i in args['items'] if i.get('number')]
        if merge_items:
            item_commit = self.doMergeChanges(
                merger, merge_items, repo_state, restored_repos)
            if item_commit is None:
                # There was a merge conflict and we have already sent
                # a work complete result, don't run any jobs
                return

        # Early abort if abort requested
        if self.aborted:
            self._send_aborted()
            return

        for project in args['projects']:
            if (project['connection'], project['name']) in restored_repos:
                continue
            merger.setRepoState(
                project['connection'], project['name'], repo_state,
                process_worker=self.executor_server.process_worker)

        # Early abort if abort requested
        if self.aborted:
            self._send_aborted()
            return

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

        # Early abort if abort requested
        if self.aborted:
            self._send_aborted()
            return

        # We set the nodes to "in use" as late as possible. So in case
        # the build failed during the checkout phase, the node is
        # still untouched and nodepool can re-allocate it to a
        # different node request / build.  Below this point, we may
        # start to run tasks on nodes (prepareVars in particular uses
        # Ansible to freeze hostvars).
        if self.node_request:
            tenant_name = self.arguments["zuul"]["tenant"]
            project_name = self.arguments["zuul"]["project"]["canonical_name"]
            self.executor_server.nodepool.useNodeSet(
                self.nodeset, tenant_name, project_name, self.zuul_event_id)

        # This prepares each playbook and the roles needed for each.
        self.preparePlaybooks(args)
        self.writeLoggingConfig()
        zuul_resources = self.prepareNodes(args)  # set self.host_list
        self.prepareVars(args, zuul_resources)   # set self.original_hostvars
        self.writeDebugInventory()

        # Early abort if abort requested
        if self.aborted:
            self._send_aborted()
            return

        data = self._base_job_data()
        if self.executor_server.log_streaming_port != DEFAULT_FINGER_PORT:
            data['url'] = "finger://{hostname}:{port}/{uuid}".format(
                hostname=self.executor_server.hostname,
                port=self.executor_server.log_streaming_port,
                uuid=self.build_request.uuid)
        else:
            data['url'] = 'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=self.build_request.uuid)

        self.executor_server.updateBuildStatus(self.build_request, data)

        result = self.runPlaybooks(args)
        success = result == 'SUCCESS'

        self.runCleanupPlaybooks(success)

        # Stop the persistent SSH connections.
        setup_status, setup_code = self.runAnsibleCleanup(
            self.jobdir.setup_playbook)

        if self.aborted_reason == self.RESULT_DISK_FULL:
            result = 'DISK_FULL'
        data, secret_data = self.getResultData()
        warnings = []
        self.mapLines(merger, args, data, item_commit, warnings)
        warnings.extend(get_warnings_from_result_data(data, logger=self.log))
        result_data = dict(result=result,
                           warnings=warnings,
                           data=data,
                           secret_data=secret_data)
        # TODO do we want to log the secret data here?
        self.log.debug("Sending result: %s", result_data)
        self.executor_server.completeBuild(self.build_request, result_data)


class ExecutorServer(BaseMergeServer):
    log = logging.getLogger("zuul.ExecutorServer")
    _ansible_manager_class = AnsibleManager
    _job_class = AnsibleJobZK
    _repo_locks_class = RepoLocks

    # Number of seconds past node expiration a hold request will remain
    EXPIRED_HOLD_REQUEST_TTL = 24 * 60 * 60

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
        self.keystore = KeyStorage(
            self.zk_client,
            password=self._get_key_store_password())
        self._running = False
        self._command_running = False
        # TODOv3(mordred): make the executor name more unique --
        # perhaps hostname+pid.
        self.hostname = get_default(self.config, 'executor', 'hostname',
                                    socket.getfqdn())
        self.component_info = ExecutorComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()
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

        # Those attributes won't change, so it's enough to set them once on the
        # component info.
        self.component_info.zone = self.zone
        self.component_info.allow_unzoned = self.allow_unzoned

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
        self.accepting_work = True
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
        self.component_info.process_merge_jobs = self.process_merge_jobs

        self.system = ZuulSystem(self.zk_client)
        self.nodepool = Nodepool(self.zk_client, self.system.system_id,
                                 self.statsd)

        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client)
        self.build_worker = threading.Thread(
            target=self.runBuildWorker,
            name="ExecutorServerBuildWorkerThread",
        )

        self.build_loop_wake_event = threading.Event()

        zone_filter = [self.zone]
        if self.allow_unzoned:
            # In case we are allowed to execute unzoned jobs, make sure, we are
            # subscribed to the default zone.
            zone_filter.append(None)

        self.executor_api = ExecutorApi(
            self.zk_client,
            zone_filter=zone_filter,
            build_request_callback=self.build_loop_wake_event.set,
            build_event_callback=self._handleBuildEvent,
        )

        # Used to offload expensive operations to different processes
        self.process_worker = None

    def _get_key_store_password(self):
        try:
            return self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")

    def _repoLock(self, connection_name, project_name):
        return self.repo_locks.getRepoLock(connection_name, project_name)

    # We use a property to reflect the accepting_work state on the component
    # since it might change quite often.
    @property
    def accepting_work(self):
        return self.component_info.accepting_work

    @accepting_work.setter
    def accepting_work(self, work):
        self.component_info.accepting_work = work

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

        self.build_worker.start()

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
        self.component_info.state = self.component_info.RUNNING

    def register_work(self):
        if self._running:
            self.accepting_work = True
            self.build_loop_wake_event.set()

    def unregister_work(self):
        self.accepting_work = False

    def stop(self):
        self.log.debug("Stopping")
        self.component_info.state = self.component_info.STOPPED
        self.connections.stop()
        self.disk_accountant.stop()
        # The governor can change function registration, so make sure
        # it has stopped.
        self.governor_stop_event.set()
        self.governor_thread.join()
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
        # build and merger workers.
        self.build_loop_wake_event.set()
        self.build_worker.join()

        if self.process_worker is not None:
            self.process_worker.shutdown()

        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.gauge(base_key + '.load_average', 0)
            self.statsd.gauge(base_key + '.pct_used_ram', 0)
            self.statsd.gauge(base_key + '.running_builds', 0)

        # Use the BaseMergeServer's stop method to disconnect from
        # ZooKeeper.  We do this as one of the last steps to ensure
        # that all ZK related components can be stopped first.
        super().stop()
        self.stop_repl()
        self.log.debug("Stopped")

    def join(self):
        self.governor_thread.join()
        for update_thread in self.update_threads:
            update_thread.join()
        if self.process_merge_jobs:
            super().join()
        self.build_loop_wake_event.set()
        self.build_worker.join()
        self.command_thread.join()

    def pause(self):
        self.log.debug('Pausing')
        self.component_info.state = self.component_info.PAUSED
        self.pause_sensor.pause = True
        if self.process_merge_jobs:
            super().pause()

    def unpause(self):
        self.log.debug('Resuming')
        self.component_info.state = self.component_info.RUNNING
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
                source = self.connections.getSource(task.connection_name)
                project = source.getProject(task.project_name)
                task.canonical_name = project.canonical_name
                log.debug("Finished updating repo %s/%s",
                          task.connection_name, task.project_name)
                task.success = True
        except BrokenProcessPool:
            # The process pool got broken. Reset it to unbreak it for further
            # requests.
            log.exception('Process pool got broken')
            self.resetProcessPool()
            task.transient_error = True
        except Exception:
            log.exception('Got exception while updating repo %s/%s',
                          task.connection_name, task.project_name)
        finally:
            task.setComplete()

    def update(self, connection_name, project_name, repo_state=None,
               zuul_event_id=None, build=None):
        # Update a repository in the main merger

        task = UpdateTask(connection_name, project_name, repo_state=repo_state,
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

    def executeJob(self, build_request, params):
        zuul_event_id = params['zuul_event_id']
        log = get_annotated_logger(self.log, zuul_event_id)
        log.debug(
            "Got %s job: %s",
            params["zuul"]["job"],
            build_request.uuid,
        )
        if self.statsd:
            base_key = 'zuul.executor.{hostname}'
            self.statsd.incr(base_key + '.builds')
        self.job_workers[build_request.uuid] = self._job_class(
            self, build_request, params
        )
        # Run manageLoad before starting the thread mostly for the
        # benefit of the unit tests to make the calculation of the
        # number of starting jobs more deterministic.
        self.manageLoad()
        self.job_workers[build_request.uuid].run()

    def _handleBuildEvent(self, build_request, build_event):
        log = get_annotated_logger(
            self.log, build_request.event_id, build=build_request.uuid)
        log.debug(
            "Received %s event for build %s", build_event.name, build_request)
        # Fulfill the resume/cancel requests after our internal calls
        # to aid the test suite in avoiding races.
        if build_event == JobRequestEvent.CANCELED:
            self.stopJob(build_request)
            self.executor_api.fulfillCancel(build_request)
        elif build_event == JobRequestEvent.RESUMED:
            self.resumeJob(build_request)
            self.executor_api.fulfillResume(build_request)
        elif build_event == JobRequestEvent.DELETED:
            self.stopJob(build_request)

    def runBuildWorker(self):
        while self._running:
            self.build_loop_wake_event.wait()
            self.build_loop_wake_event.clear()
            try:
                for build_request in self.executor_api.next():
                    # Check the sensors again as they might have changed in the
                    # meantime. E.g. the last build started within the next()
                    # generator could have fulfilled the StartingBuildSensor.
                    if not self.accepting_work:
                        break
                    if not self._running:
                        break
                    self._runBuildWorker(build_request)
            except Exception:
                self.log.exception("Error in build loop:")
                time.sleep(5)

    def _runBuildWorker(self, build_request: BuildRequest):
        log = get_annotated_logger(
            self.log, event=None, build=build_request.uuid
        )
        # Lock and update the build request
        if not self.executor_api.lock(build_request, blocking=False):
            return

        # Ensure that the request is still in state requested. This method is
        # called based on cached data and there might be a mismatch between the
        # cached state and the real state of the request. The lock might
        # have been successful because the request is already completed and
        # thus unlocked.
        if build_request.state != BuildRequest.REQUESTED:
            self._retry(build_request.lock, log, self.executor_api.unlock,
                        build_request)

        try:
            params = self.executor_api.getParams(build_request)
            # Directly update the build in ZooKeeper, so we don't loop
            # over and try to lock it again and again.  Do this before
            # clearing the params so if we fail, no one tries to
            # re-run the job.
            build_request.state = BuildRequest.RUNNING
            # Set the hostname on the build request so it can be used by
            # zuul-web for the live log streaming.
            build_request.worker_info = {
                "hostname": self.hostname,
                "log_port": self.log_streaming_port,
            }
            self.executor_api.update(build_request)
        except Exception:
            log.exception("Exception while preparing to start worker")
            # If we failed at this point, we have not written anything
            # to ZK yet; the only thing we need to do is to ensure
            # that we release the lock, and another executor will be
            # able to grab the build.
            self._retry(build_request.lock, log, self.executor_api.unlock,
                        build_request)
            return

        try:
            self.executor_api.clearParams(build_request)
            log.debug("Next executed job: %s", build_request)
            self.executeJob(build_request, params)
        except Exception:
            # Note, this is not a finally clause, because if we
            # sucessfuly start executing the job, it's the
            # AnsibleJob's responsibility to call completeBuild and
            # unlock the request.
            log.exception("Exception while starting worker")
            result = {
                "result": "ERROR",
                "exception": traceback.format_exc(),
            }
            self.completeBuild(build_request, result)

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
        self.log.debug(
            "Finishing Job: %s, queue(%d): %s",
            unique,
            len(self.job_workers),
            self.job_workers,
        )

    def stopJobDiskFull(self, jobdir):
        unique = os.path.basename(jobdir)
        self.stopJobByUnique(unique, reason=AnsibleJob.RESULT_DISK_FULL)

    def resumeJob(self, build_request):
        log = get_annotated_logger(
            self.log, build_request.event_id, build=build_request.uuid)
        log.debug("Resume job")
        self.resumeJobByUnique(
            build_request.uuid, build_request.event_id
        )

    def stopJob(self, build_request):
        log = get_annotated_logger(
            self.log, build_request.event_id, build=build_request.uuid)
        log.debug("Stop job")
        self.stopJobByUnique(build_request.uuid, build_request.event_id)

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

    def _handleExpiredHoldRequest(self, request):
        '''
        Check if a hold request is expired and delete it if it is.

        The 'expiration' attribute will be set to the clock time when the
        hold request was used for the last time. If this is NOT set, then
        the request is still active.

        If a node expiration time is set on the request, and the request is
        expired, *and* we've waited for a defined period past the node
        expiration (EXPIRED_HOLD_REQUEST_TTL), then we will delete the hold
        request.

        :param: request Hold request
        :returns: True if it is expired, False otherwise.
        '''
        if not request.expired:
            return False

        if not request.node_expiration:
            # Request has been used up but there is no node expiration, so
            # we don't auto-delete it.
            return True

        elapsed = time.time() - request.expired
        if elapsed < self.EXPIRED_HOLD_REQUEST_TTL + request.node_expiration:
            # Haven't reached our defined expiration lifetime, so don't
            # auto-delete it yet.
            return True

        try:
            self.nodepool.zk_nodepool.lockHoldRequest(request)
            self.log.info("Removing expired hold request %s", request)
            self.nodepool.zk_nodepool.deleteHoldRequest(request)
        except Exception:
            self.log.exception(
                "Failed to delete expired hold request %s", request
            )
        finally:
            try:
                self.nodepool.zk_nodepool.unlockHoldRequest(request)
            except Exception:
                pass

        return True

    def _getAutoholdRequest(self, args):
        autohold_key_base = (
            args["zuul"]["tenant"],
            args["zuul"]["project"]["canonical_name"],
            args["zuul"]["job"],
        )

        class Scope(object):
            """Enum defining a precedence/priority of autohold requests.

            Autohold requests for specific refs should be fulfilled first,
            before those for changes, and generic jobs.

            Matching algorithm goes over all existing autohold requests, and
            returns one with the highest number (in case of duplicated
            requests the last one wins).
            """
            NONE = 0
            JOB = 1
            CHANGE = 2
            REF = 3

        # Do a partial match of the autohold key against all autohold
        # requests, ignoring the last element of the key (ref filter),
        # and finally do a regex match between ref filter from
        # the autohold request and the build's change ref to check
        # if it matches. Lastly, make sure that we match the most
        # specific autohold request by comparing "scopes"
        # of requests - the most specific is selected.
        autohold = None
        scope = Scope.NONE
        self.log.debug("Checking build autohold key %s", autohold_key_base)
        for request_id in self.nodepool.zk_nodepool.getHoldRequests():
            request = self.nodepool.zk_nodepool.getHoldRequest(request_id)
            if not request:
                continue

            if self._handleExpiredHoldRequest(request):
                continue

            ref_filter = request.ref_filter

            if request.current_count >= request.max_count:
                # This request has been used the max number of times
                continue
            elif not (
                request.tenant == autohold_key_base[0]
                and request.project == autohold_key_base[1]
                and request.job == autohold_key_base[2]
            ):
                continue
            elif not re.match(ref_filter, args["zuul"]["ref"]):
                continue

            if ref_filter == ".*":
                candidate_scope = Scope.JOB
            elif ref_filter.endswith(".*"):
                candidate_scope = Scope.CHANGE
            else:
                candidate_scope = Scope.REF

            self.log.debug(
                "Build autohold key %s matched scope %s",
                autohold_key_base,
                candidate_scope,
            )
            if candidate_scope > scope:
                scope = candidate_scope
                autohold = request

        return autohold

    def _processAutohold(self, ansible_job, duration, result):
        # We explicitly only want to hold nodes for jobs if they have
        # failed / retry_limit / post_failure and have an autohold request.
        hold_list = ["FAILURE", "RETRY_LIMIT", "POST_FAILURE", "TIMED_OUT"]
        if result not in hold_list:
            return False

        request = self._getAutoholdRequest(ansible_job.arguments)
        if request is not None:
            self.log.debug("Got autohold %s", request)
            self.nodepool.holdNodeSet(
                ansible_job.nodeset, request, ansible_job.build_request,
                duration, ansible_job.zuul_event_id)
            return True
        return False

    def startBuild(self, build_request, data):
        data["start_time"] = time.time()

        event = BuildStartedEvent(
            build_request.uuid, build_request.build_set_uuid,
            build_request.job_name, build_request.path, data,
            build_request.event_id)
        self.result_events[build_request.tenant_name][
            build_request.pipeline_name].put(event)

    def updateBuildStatus(self, build_request, data):
        event = BuildStatusEvent(
            build_request.uuid, build_request.build_set_uuid,
            build_request.job_name, build_request.path, data,
            build_request.event_id)
        self.result_events[build_request.tenant_name][
            build_request.pipeline_name].put(event)

    def pauseBuild(self, build_request, data):
        build_request.state = BuildRequest.PAUSED
        try:
            self.executor_api.update(build_request)
        except JobRequestNotFound as e:
            self.log.warning("Could not pause build: %s", str(e))
            return

        event = BuildPausedEvent(
            build_request.uuid, build_request.build_set_uuid,
            build_request.job_name, build_request.path, data,
            build_request.event_id)
        self.result_events[build_request.tenant_name][
            build_request.pipeline_name].put(event)

    def resumeBuild(self, build_request):
        build_request.state = BuildRequest.RUNNING
        try:
            self.executor_api.update(build_request)
        except JobRequestNotFound as e:
            self.log.warning("Could not resume build: %s", str(e))
            return

    def completeBuild(self, build_request, result):
        result["end_time"] = time.time()

        log = get_annotated_logger(self.log, build_request.event_id,
                                   build=build_request.uuid)

        # NOTE (felix): We store the end_time on the ansible job to calculate
        # the in-use duration of locked nodes when the nodeset is returned.
        # NOTE: this method may be called before we create a job worker.
        ansible_job = self.job_workers.get(build_request.uuid)
        if ansible_job:
            ansible_job.end_time = time.monotonic()
            duration = ansible_job.end_time - ansible_job.time_starting_build

            params = ansible_job.arguments
            # If the result is None, check if the build has reached
            # its max attempts and if so set the result to
            # RETRY_LIMIT.  This must be done in order to correctly
            # process the autohold in the next step. Since we only
            # want to hold the node if the build has reached a final
            # result.
            if result.get("result") is None:
                attempts = params["zuul"]["attempts"]
                max_attempts = params["max_attempts"]
                if attempts >= max_attempts:
                    result["result"] = "RETRY_LIMIT"

            # Provide the hold information back to the scheduler via the build
            # result.
            try:
                held = self._processAutohold(ansible_job, duration,
                                             result.get("result"))
                result["held"] = held
                log.info("Held status set to %s", held)
            except Exception:
                log.exception("Unable to process autohold for %s",
                              build_request)

        def update_build_request(log, build_request):
            try:
                self.executor_api.update(build_request)
                return True
            except JobRequestNotFound as e:
                log.warning("Could not find build: %s", str(e))
                return False

        def put_complete_event(log, build_request, event):
            try:
                self.result_events[build_request.tenant_name][
                    build_request.pipeline_name].put(event)
            except NoNodeError:
                log.warning("Pipeline was removed: %s",
                            build_request.pipeline_name)

        build_request.state = BuildRequest.COMPLETED
        found = self._retry(build_request.lock, log,
                            update_build_request, log, build_request)
        lock_valid = build_request.lock.is_still_valid()
        if lock_valid:
            # We only need to unlock if we're still locked.
            self._retry(build_request.lock, log, self.executor_api.unlock,
                        build_request)

        if not found:
            # If the build request is gone, don't return a result.
            return

        if not lock_valid:
            # If we lost the lock at any point before updating the
            # state to COMPLETED, then the scheduler may have (or
            # will) detect it as an incomplete build and generate an
            # error event for us.  We don't need to submit a
            # completion event in that case.
            #
            # TODO: If we make the scheduler robust against receiving
            # duplicate completion events for the same build, we could
            # choose continue here and submit the completion event in
            # the hopes that we would win the race against the cleanup
            # thread.  That might (in some narrow circumstances)
            # rescue an otherwise acceptable build from being
            # discarded.
            return

        # TODO: This is racy.  Once we have set the build request to
        # completed, the only way for it to be deleted is for the
        # scheduler to process a BuildRequestCompleted event.  So we
        # need to try really hard to give it one.  But if we exit
        # between the section above and the section below, we won't,
        # which will mean that the scheduler will not automatically
        # delete the build request and we will not be able to recover.
        #
        # This is essentially a two-phase commit problem, but we are
        # unable to use transactions because the result event is
        # sharded.  We should be able to redesign the result reporting
        # mechanism to eliminate the race and be more convergent.
        event = BuildCompletedEvent(
            build_request.uuid, build_request.build_set_uuid,
            build_request.job_name, build_request.path, result,
            build_request.event_id)
        self._retry(None, log, put_complete_event, log,
                    build_request, event)
