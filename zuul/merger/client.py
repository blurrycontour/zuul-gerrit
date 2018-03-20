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
import threading
from uuid import uuid4

import gear

import zuul.model
from zuul.lib.config import get_default
from zuul.lib.logutil import get_annotated_logger


def getJobData(job):
    if not len(job.data):
        return {}
    d = job.data[-1]
    if not d:
        return {}
    return json.loads(d)


class MergeGearmanClient(gear.Client):
    def handleWorkComplete(self, packet):
        job = super(MergeGearmanClient, self).handleWorkComplete(packet)
        job.merge_job.finish_attempt(success=True)
        return job

    def handleWorkFail(self, packet):
        job = super(MergeGearmanClient, self).handleWorkComplete(packet)
        job.merge_job.finish_attempt(success=False)
        return job

    def handleWorkException(self, packet):
        job = super(MergeGearmanClient, self).handleWorkComplete(packet)
        job.merge_job.finish_attempt(success=False)
        return job

    def handleDisconnect(self, packet):
        job = super(MergeGearmanClient, self).handleWorkComplete(packet)
        job.merge_job.finish_attempt(success=False)
        return job


class MergeJob(object):
    """A job that can be waited upon until complete or all
    retries exhausted"""
    MAX_ATTEMPTS = 3

    def __init__(self, merge_client, job_name, data, build_set,
                 precedence=zuul.model.PRECEDENCE_NORMAL, event=None):
        log = logging.getLogger("zuul.MergeJob")
        self.log = get_annotated_logger(log, event)
        self.merge_client = merge_client
        self.name = job_name
        self.job_data = data
        self.build_set = build_set
        self.precedence = precedence
        self.timeout = 300
        self.__wait_event = threading.Event()
        self._attempts = 0
        self._job_running = False

    def start_attempt(self):
        if self._job_running:
            raise Exception("MergeJob attempt already running")
        self._attempts += 1
        uuid = str(uuid4().hex)
        self.gearman_job = gear.TextJob(
            self.name,
            json.dumps(self.job_data),
            unique=uuid
        )
        self.gearman_job.merge_job = self
        self.log.debug("Submitting job %s with data %s", self, self.job_data)
        self.merge_client.gearman.submitJob(
            self.gearman_job,
            precedence=self.precedence,
            timeout=self.timeout
        )
        self._job_running = True

    def finish_attempt(self, success):
        """Called when gearman is finished with the job for whatever
        reason including failures and execptions.

        :arg bool success: Whether or not the job finished successfully"""
        if not self._job_running:
            raise Exception("Not expecting a job to finish")
        self._job_running = False
        if not success:
            if self._attempts <= self.MAX_ATTEMPTS:
                self.start_attempt()
                return
        self.merge_client.onBuildCompleted(self)

    def setComplete(self):
        self.__wait_event.set()

    def wait(self, timeout=300):
        return self.__wait_event.wait(timeout)


class MergeClient(object):
    log = logging.getLogger("zuul.MergeClient")

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        server = self.config.get('gearman', 'server')
        port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        self.log.debug("Connecting to gearman at %s:%s" % (server, port))
        self.gearman = MergeGearmanClient()
        self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca,
                               keepalive=True, tcp_keepidle=60,
                               tcp_keepintvl=30, tcp_keepcnt=5)
        self.git_timeout = get_default(
            self.config, 'merger', 'git_timeout', 300)
        self.log.debug("Waiting for gearman")
        self.gearman.waitForServer()
        self.jobs = set()

    def stop(self):
        self.gearman.shutdown()

    def areMergesOutstanding(self):
        if self.jobs:
            return True
        return False

    def startJob(self, name, data, build_set,
                 precedence=zuul.model.PRECEDENCE_NORMAL, event=None):
        job = MergeJob(self, name, data, build_set, precedence, event=event)
        self.jobs.add(job)
        job.start_attempt()
        return job

    def mergeChanges(self, items, build_set, files=None, dirs=None,
                     repo_state=None, precedence=zuul.model.PRECEDENCE_NORMAL,
                     event=None):
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None
        data = dict(items=items,
                    files=files,
                    dirs=dirs,
                    repo_state=repo_state,
                    zuul_event_id=zuul_event_id)
        return self.startJob('merger:merge', data, build_set, precedence,
                             event=event)

    def getRepoState(self, items, build_set,
                     precedence=zuul.model.PRECEDENCE_NORMAL,
                     event=None):
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(items=items, zuul_event_id=zuul_event_id)
        return self.startJob('merger:refstate', data, build_set, precedence,
                             event=event)

    def getFiles(self, connection_name, project_name, branch, files, dirs=[],
                 precedence=zuul.model.PRECEDENCE_HIGH, event=None):
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    files=files,
                    dirs=dirs,
                    zuul_event_id=zuul_event_id)
        job = self.startJob('merger:cat', data, None, precedence, event=event)
        return job

    def getFilesChanges(self, connection_name, project_name, branch,
                        tosha=None, precedence=zuul.model.PRECEDENCE_HIGH,
                        build_set=None, event=None):
        if event is not None:
            zuul_event_id = event.zuul_event_id
        else:
            zuul_event_id = None

        data = dict(connection=connection_name,
                    project=project_name,
                    branch=branch,
                    tosha=tosha,
                    zuul_event_id=zuul_event_id)
        job = self.startJob('merger:fileschanges', data, build_set,
                            precedence, event=event)
        return job

    def onBuildCompleted(self, job):
        data = getJobData(job.gearman_job)
        zuul_event_id = data.get('zuul_event_id')
        log = get_annotated_logger(self.log, zuul_event_id)

        merged = data.get('merged', False)
        job.updated = data.get('updated', False)
        commit = data.get('commit')
        files = data.get('files', {})
        repo_state = data.get('repo_state', {})
        job.files = files
        log.info("Merge %s complete, merged: %s, updated: %s, "
                 "commit: %s", job, merged, job.updated, commit)
        job.setComplete()
        if job.build_set:
            if job.name == 'merger:fileschanges':
                self.sched.onFilesChangesCompleted(job.build_set, files)
            else:
                self.sched.onMergeCompleted(job.build_set,
                                            merged, job.updated, commit, files,
                                            repo_state)

        # The test suite expects the job to be removed from the
        # internal account after the wake flag is set.
        self.jobs.remove(job)
