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

import logging
import os
import socket
import threading
import time
from abc import ABCMeta
from configparser import ConfigParser

from kazoo.exceptions import BadVersionError

from zuul.lib import commandsocket
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger
from zuul.merger import merger
from zuul.merger.merger import nullcontext
from zuul.model import (
    FilesChangesCompletedEvent,
    MergeCompletedEvent,
    MergeRequestState,
    MergeRequestType,
)
from zuul.zk import ZooKeeperClient
from zuul.zk.components import ComponentState, MergerComponent
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.merger import MergerApi

COMMANDS = ['stop', 'pause', 'unpause']


class BaseRepoLocks(metaclass=ABCMeta):

    def getRepoLock(self, connection_name, project_name):
        return nullcontext()


class RepoLocks(BaseRepoLocks):

    def __init__(self):
        self.locks = {}

    def getRepoLock(self, connection_name, project_name):
        key = '%s:%s' % (connection_name, project_name)
        self.locks.setdefault(key, threading.Lock())
        return self.locks[key]


class BaseMergeServer(metaclass=ABCMeta):
    log = logging.getLogger("zuul.BaseMergeServer")

    _repo_locks_class = BaseRepoLocks

    def __init__(
        self,
        config: ConfigParser,
        component: str,
        connections,
    ):
        self.connections = connections
        self._merger_running = False
        self.merge_email = get_default(config, 'merger', 'git_user_email',
                                       'zuul.merger.default@example.com')
        self.merge_name = get_default(config, 'merger', 'git_user_name',
                                      'Zuul Merger Default')
        self.merge_speed_limit = get_default(
            config, 'merger', 'git_http_low_speed_limit', '1000')
        self.merge_speed_time = get_default(
            config, 'merger', 'git_http_low_speed_time', '30')
        self.git_timeout = get_default(config, 'merger', 'git_timeout', 300)

        self.merge_root = get_default(config, component, 'git_dir',
                                      '/var/lib/zuul/{}-git'.format(component))

        self.config = config

        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        self.merger_worker = threading.Thread(
            target=self.runMergerWorker,
            name="MergerServerMergerWorkerThread",
        )

        self.merger_cleanup_worker = threading.Thread(
            target=self.runMergerCleanupWorker,
            name="MergerServerCleanupWorkerThread",
        )

        self.merger_loop_wake_event = threading.Event()
        self.merger_cleanup_election = self.zk_client.client.Election(
            f"{MergerApi.MERGE_REQUEST_ROOT}/election"
        )

        self.merger_api = MergerApi(
            self.zk_client,
            merge_request_callback=self.merger_loop_wake_event.set,
        )

        # This merger and its git repos are used to maintain
        # up-to-date copies of all the repos that are used by jobs, as
        # well as to support the merger:cat functon to supply
        # configuration information to Zuul when it starts.
        self.merger = self._getMerger(self.merge_root, None)

        # Repo locking is needed on the executor
        self.repo_locks = self._repo_locks_class()

    def _getMerger(self, root, cache_root, logger=None):
        return merger.Merger(
            root,
            self.connections,
            self.zk_client,
            self.merge_email,
            self.merge_name,
            self.merge_speed_limit,
            self.merge_speed_time,
            cache_root,
            logger,
            execution_context=True,
            git_timeout=self.git_timeout,
        )

    def _repoLock(self, connection_name, project_name):
        # The merger does not need locking so return a null lock.
        return nullcontext()

    def _update(self, connection_name, project_name, zuul_event_id=None):
        self.merger.updateRepo(connection_name, project_name,
                               zuul_event_id=zuul_event_id)

    def start(self):
        self.log.debug('Starting merger worker')
        self._merger_running = True
        self.log.debug('Cleaning any stale git index.lock files')
        for (dirpath, dirnames, filenames) in os.walk(self.merge_root):
            if '.git' in dirnames:
                # Only recurse into .git dirs
                dirnames.clear()
                dirnames.append('.git')
            elif dirpath.endswith('/.git'):
                # Recurse no further
                dirnames.clear()
                if 'index.lock' in filenames:
                    fp = os.path.join(dirpath, 'index.lock')
                    try:
                        os.unlink(fp)
                        self.log.debug('Removed stale git lock: %s' % fp)
                    except Exception:
                        self.log.exception(
                            'Unable to remove stale git lock: '
                            '%s this may result in failed merges' % fp)
        self.merger_worker.start()
        self.merger_cleanup_worker.start()

    def stop(self):
        self.log.debug('Stopping merger worker')
        self._merger_running = False
        self.merger_loop_wake_event.set()
        self.merger_worker.join()
        self.merger_cleanup_election.cancel()
        self.merger_cleanup_worker.join()
        self.zk_client.disconnect()

    def join(self):
        self.merger_loop_wake_event.set()
        self.merger_worker.join()
        self.merger_cleanup_worker.join()

    def pause(self):
        self.log.debug('Pausing merger worker')
        # TODO (felix): How to pause/unpause the merger worker? We could pause
        # the Merger API as well, so any cache updates don't set the wake
        # event. Not sure if that is a proper solution though.

    def unpause(self):
        self.log.debug('Resuming merger worker')

    def runMergerCleanupWorker(self):
        while self._merger_running:
            try:
                self.merger_cleanup_election.run(self._runMergerCleanupWorker)
            except Exception:
                self.log.exception("Exception in merger cleanup worker")

    def _runMergerCleanupWorker(self):
        while self._merger_running:
            for merge_request in self.merger_api.lostMergeRequests():
                try:
                    self.completeMergeJob(merge_request, None)
                except BadVersionError:
                    # There could be a race condition:
                    # The merge request is found by lost_merge_requests in
                    # state RUNNING but gets completed/unlocked before the
                    # is_locked() check. Since we use the znode version, the
                    # update will fail in this case and we can simply ignore
                    # the exception.
                    pass
                if not self._merger_running:
                    return
            # TODO (felix): It should be enough to execute the cleanup every
            # 60 minutes. Find a proper way to do that. Maybe we could combine
            # this with other cleanups in the scheduler and use APScheduler for
            # proper scheduling.
            time.sleep(5)

    def runMergerWorker(self):
        self.log.debug("FE: runMergerWorker")
        while self._merger_running:
            self.log.debug("FE: Waiting for wake event")
            self.merger_loop_wake_event.wait()
            self.merger_loop_wake_event.clear()
            for merge_request in self.merger_api.next():
                if not self._merger_running:
                    break
                self._runMergerWorker(merge_request)

    def _runMergerWorker(self, merge_request):
        if not self.merger_api.lock(merge_request, blocking=False):
            return

        merge_request.state = MergeRequestState.RUNNING
        # Directly update the merge request in ZooKeeper, so we don't loop over
        # and try to lock it again and again.
        self.merger_api.update(merge_request)
        # TODO (felix): What about the executor server implementation
        # when it's currently not accepting work? Do we have to ignore
        # merge requests in that case as well?
        self.log.debug("Next executed merge job: %s", merge_request)
        self.executeMergeJob(merge_request)

    def executeMergeJob(self, merge_request):
        result = None
        if merge_request.job_type == MergeRequestType.MERGE:
            result = self.merge(merge_request)
        elif merge_request.job_type == MergeRequestType.CAT:
            result = self.cat(merge_request)
        elif merge_request.job_type == MergeRequestType.REF_STATE:
            result = self.refstate(merge_request)
        elif merge_request.job_type == MergeRequestType.FILES_CHANGES:
            result = self.fileschanges(merge_request)

        # if not result:
            # TODO (felix): Even without a result we should complete the job,
            # so it is removed from ZK.
        #    return

        self.completeMergeJob(merge_request, result)

    def cat(self, merge_request):
        self.log.debug("Got cat job: %s", merge_request.uuid)
        args = merge_request.payload

        connection_name = args['connection']
        project_name = args['project']

        lock = self.repo_locks.getRepoLock(connection_name, project_name)
        try:
            self._update(connection_name, project_name)
            with lock:
                files = self.merger.getFiles(connection_name, project_name,
                                             args['branch'], args['files'],
                                             args.get('dirs'))
        except Exception:
            result = dict(update=False)
        else:
            result = dict(updated=True, files=files)

        return result

    def merge(self, merge_request):
        self.log.debug("Got merge job: %s", merge_request.uuid)
        args = merge_request.payload
        zuul_event_id = args.get('zuul_event_id')

        ret = self.merger.mergeChanges(
            args['items'], args.get('files'),
            args.get('dirs', []),
            args.get('repo_state'),
            branches=args.get('branches'),
            repo_locks=self.repo_locks,
            zuul_event_id=zuul_event_id)

        result = dict(merged=(ret is not None))
        if ret is None:
            result['commit'] = result['files'] = result['repo_state'] = None
        else:
            (result['commit'], result['files'], result['repo_state'],
             recent, orig_commit) = ret
        result['zuul_event_id'] = zuul_event_id
        return result

    def refstate(self, merge_request):
        self.log.debug("Got refstate job: %s", merge_request.uuid)
        args = merge_request.payload
        zuul_event_id = args.get('zuul_event_id')
        success, repo_state, item_in_branches = \
            self.merger.getRepoState(
                args['items'], branches=args.get('branches'),
                repo_locks=self.repo_locks)
        result = dict(updated=success,
                      repo_state=repo_state,
                      item_in_branches=item_in_branches)
        result['zuul_event_id'] = zuul_event_id
        return result

    def fileschanges(self, merge_request):
        self.log.debug("Got fileschanges job: %s", merge_request.uuid)
        args = merge_request.payload
        zuul_event_id = args.get('zuul_event_id')

        connection_name = args['connection']
        project_name = args['project']

        lock = self.repo_locks.getRepoLock(connection_name, project_name)
        try:
            self._update(connection_name, project_name,
                         zuul_event_id=zuul_event_id)
            with lock:
                files = self.merger.getFilesChanges(
                    connection_name, project_name,
                    args['branch'], args['tosha'],
                    zuul_event_id=zuul_event_id)
        except Exception:
            result = dict(update=False)
        else:
            result = dict(updated=True, files=files)

        result['zuul_event_id'] = zuul_event_id
        return result

    def completeMergeJob(self, merge_request, result):
        log = get_annotated_logger(
            self.log, merge_request.payload.get("zuul_event_id")
        )

        if result is not None:
            merged = result.get("merged", False)
            updated = result.get("updated", False)
            commit = result.get("commit")
            repo_state = result.get("repo_state", {})
            item_in_branches = result.get("item_in_branches", [])
            files = result.get("files", {})

            log.info(
                "Merge %s complete, merged: %s, updated: %s, commit: %s, "
                "branches: %s",
                merge_request,
                merged,
                updated,
                commit,
                item_in_branches,
            )

            # Provide a result either via a result future or a result event
            if merge_request.result_path:
                self.merger_api.reportResult(merge_request, result)

            if merge_request.build_set_uuid:
                if merge_request.job_type == MergeRequestType.FILES_CHANGES:
                    event = FilesChangesCompletedEvent(
                        merge_request.build_set_uuid,
                        merge_request.queue_name,
                        files,
                    )
                else:
                    event = MergeCompletedEvent(
                        merge_request.build_set_uuid,
                        merge_request.queue_name,
                        merged,
                        updated,
                        commit,
                        files,
                        repo_state,
                        item_in_branches,
                    )

                tenant_name = merge_request.tenant_name
                pipeline_name = merge_request.pipeline_name

                self.result_events[tenant_name][pipeline_name].put(event)

        # Set the merge request to completed, unlock and delete it. Although
        # the state update is mainly for consistency reasonns, it might come in
        # handy in case the deletion or unlocking failes. Thus, we know that
        # the merge request was already processed and we have a result in the
        # result queue.
        merge_request.state = MergeRequestState.COMPLETED
        self.merger_api.update(merge_request)
        self.merger_api.unlock(merge_request)
        self.merger_api.remove(merge_request)


class MergeServer(BaseMergeServer):
    log = logging.getLogger("zuul.MergeServer")

    def __init__(
        self,
        config: ConfigParser,
        connections,
    ):
        super().__init__(config, 'merger', connections)
        self.hostname = socket.getfqdn()
        self.component_info = MergerComponent(self.zk_client, self.hostname)
        self.component_info.register()

        self.command_map = dict(
            stop=self.stop,
            pause=self.pause,
            unpause=self.unpause,
        )
        command_socket = get_default(
            self.config, 'merger', 'command_socket',
            '/var/lib/zuul/merger.socket')
        self.command_socket = commandsocket.CommandSocket(command_socket)

        self._command_running = False

    def start(self):
        super().start()
        self._command_running = True
        self.log.debug("Starting command processor")
        self.command_socket.start()
        self.command_thread = threading.Thread(
            target=self.runCommand, name='command')
        self.command_thread.daemon = True
        self.command_thread.start()
        self.component_info.state = ComponentState.RUNNING

    def stop(self):
        self.log.debug("Stopping")
        self.component_info.state = ComponentState.STOPPED
        super().stop()
        self._command_running = False
        self.command_socket.stop()
        self.log.debug("Stopped")

    def join(self):
        super().join()

    def pause(self):
        self.log.debug('Pausing')
        self.component_info.state = ComponentState.PAUSED
        super().pause()

    def unpause(self):
        self.log.debug('Resuming')
        super().unpause()
        self.component_info.state = ComponentState.RUNNING

    def runCommand(self):
        while self._command_running:
            try:
                command = self.command_socket.get().decode('utf8')
                if command != '_stop':
                    self.command_map[command]()
            except Exception:
                self.log.exception("Exception while processing command")
