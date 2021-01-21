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

import json
import logging
import os
import socket
import threading
import time
from abc import ABCMeta
from configparser import ConfigParser
from typing import Optional

from zuul.zk import ZooKeeperClient

from zuul.lib.connections import ConnectionRegistry

from zuul.lib import commandsocket
from zuul.lib.config import get_default
from zuul.lib.gearworker import ZuulGearWorker
from zuul.merger import merger
from zuul.merger.merger import nullcontext
from zuul.zk.components import (
    ZooKeeperComponentRegistry, ZooKeeperComponentState
)
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.merges import MergeJobQueue, MergeJobState

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
        config: ConfigParser, component: str,
        zk_client: ZooKeeperClient,
        connections: Optional[ConnectionRegistry] = None,
    ):
        self.connections = connections or ConnectionRegistry()
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
        self.zk_client = zk_client
        self.zk_component_registry = ZooKeeperComponentRegistry(zk_client)

        self.merge_job_queue = MergeJobQueue(zk_client)

        self._merge_job_worker = threading.Thread(
            target=self._mergeJobWorkerLoop,
            name="MergerServerJobWorkerThread",
        )

        self.result_events = PipelineResultEventQueue.create_registry(
            zk_client
        )

        self._running: bool = False

        # This merger and its git repos are used to maintain
        # up-to-date copies of all the repos that are used by jobs, as
        # well as to support the merger:cat functon to supply
        # configuration information to Zuul when it starts.
        self.merger = self._getMerger(self.merge_root, None)

        self.config = config

        # Repo locking is needed on the executor
        self.repo_locks = self._repo_locks_class()

        self.merger_jobs = {
            'merger:merge': self.merge,
            'merger:cat': self.cat,
            'merger:refstate': self.refstate,
            'merger:fileschanges': self.fileschanges,
        }
        self.merger_gearworker = ZuulGearWorker(
            'Zuul Merger',
            'zuul.BaseMergeServer',
            'merger-gearman-worker',
            self.config,
            self.merger_jobs)

    def _mergeJobWorkerLoop(self):
        while self._running:
            for job in self.merge_job_queue.next():
                if not self.merge_job_queue.lock(job):
                    continue

                # TODO (felix): What about the executor server implementation
                # when it's currently not accepting work? How do we reflect
                # this for the merger jobs?
                job.state = MergeJobState.RUNNING
                # Directly update the job in ZooKeeper, so we dont loop over
                # and try to lock it again and again.
                self.merge_job_queue.update(job)
                self.log.debug("Next executed merge job: %s", job)
                # TODO (felix): Implement the job execution
            # TODO (felix): Use a wake_event instead of sleep. Who can set the
            # wake event when new jobs are in the queue? Use a data watch to
            # set the wake event.
            time.sleep(1.0)

    def _getMerger(self, root, cache_root, logger=None):
        return merger.Merger(
            root, self.connections, self.zk_client, self.merge_email,
            self.merge_name, self.merge_speed_limit, self.merge_speed_time,
            cache_root, logger, execution_context=True,
            git_timeout=self.git_timeout)

    def _repoLock(self, connection_name, project_name):
        # The merger does not need locking so return a null lock.
        return nullcontext()

    def _update(self, connection_name, project_name, zuul_event_id=None):
        self.merger.updateRepo(connection_name, project_name,
                               zuul_event_id=zuul_event_id)

    def start(self):
        self.log.debug('Starting merger worker')
        self._running = True
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
        self.merger_gearworker.start()
        self._merge_job_worker.start()

    def stop(self):
        self.log.debug('Stopping merger worker')
        self._running = False
        self.merger_gearworker.stop()
        self._merge_job_worker.join()

    def join(self):
        self.merger_gearworker.join()
        self._merge_job_worker.join()

    def pause(self):
        self.log.debug('Pausing merger worker')
        self.merger_gearworker.unregister()
        # TODO (felix): How to pause/unpause the self._merge_job_worker? The
        # executor server does that via its sensors + manageLoad(), but I want
        # to avoid implementing all this in here.

    def unpause(self):
        self.log.debug('Resuming merger worker')
        self.merger_gearworker.register()

    def cat(self, job):
        self.log.debug("Got cat job: %s" % job.unique)
        args = json.loads(job.arguments)

        connection_name = args['connection']
        project_name = args['project']
        self._update(connection_name, project_name)

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

        job.sendWorkComplete(json.dumps(result))

    def merge(self, job):
        self.log.debug("Got merge job: %s" % job.unique)
        args = json.loads(job.arguments)
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
        job.sendWorkComplete(json.dumps(result))

    def refstate(self, job):
        self.log.debug("Got refstate job: %s" % job.unique)
        args = json.loads(job.arguments)
        zuul_event_id = args.get('zuul_event_id')
        success, repo_state, item_in_branches = \
            self.merger.getRepoState(
                args['items'], branches=args.get('branches'),
                repo_locks=self.repo_locks)
        result = dict(updated=success,
                      repo_state=repo_state,
                      item_in_branches=item_in_branches)
        result['zuul_event_id'] = zuul_event_id
        job.sendWorkComplete(json.dumps(result))

    def fileschanges(self, job):
        self.log.debug("Got fileschanges job: %s" % job.unique)
        args = json.loads(job.arguments)
        zuul_event_id = args.get('zuul_event_id')

        connection_name = args['connection']
        project_name = args['project']
        self._update(connection_name, project_name,
                     zuul_event_id=zuul_event_id)

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
        job.sendWorkComplete(json.dumps(result))


class MergeServer(BaseMergeServer):
    log = logging.getLogger("zuul.MergeServer")

    def __init__(
        self,
        config: ConfigParser,
        zk_client: ZooKeeperClient,
        connections: Optional[ConnectionRegistry] = None
    ):
        super().__init__(config, 'merger', zk_client, connections)
        self.hostname = socket.getfqdn()
        self.zk_component = self.zk_component_registry.register(
            'mergers', self.hostname
        )

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
        self.zk_component.set('state', ZooKeeperComponentState.RUNNING)

    def stop(self):
        self.log.debug("Stopping")
        self.zk_component.set('state', ZooKeeperComponentState.STOPPED)
        super().stop()
        self._command_running = False
        self.command_socket.stop()
        self.log.debug("Stopped")

    def join(self):
        super().join()

    def pause(self):
        self.log.debug('Pausing')
        self.zk_component.set('state', ZooKeeperComponentState.PAUSED)
        super().pause()

    def unpause(self):
        self.log.debug('Resuming')
        super().unpause()
        self.zk_component.set('state', ZooKeeperComponentState.RUNNING)

    def runCommand(self):
        while self._command_running:
            try:
                command = self.command_socket.get().decode('utf8')
                if command != '_stop':
                    self.command_map[command]()
            except Exception:
                self.log.exception("Exception while processing command")
