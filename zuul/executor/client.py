# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

import gear
import json
import logging
import time
import threading
from uuid import uuid4

import zuul.executor.common
from zuul.lib.config import get_default
from zuul.lib.gear_utils import getGearmanFunctions
from zuul.lib.jsonutil import json_dumps
from zuul.lib.logutil import get_annotated_logger
from zuul.model import (
    Build,
    BuildCompletedEvent,
    BuildStartedEvent,
    PRECEDENCE_HIGH,
    PRECEDENCE_LOW,
    PRECEDENCE_NORMAL,
)
from zuul.zk.event_queues import PipelineResultEventQueue


class GearmanCleanup(threading.Thread):
    """ A thread that checks to see if outstanding builds have
    completed without reporting back. """
    log = logging.getLogger("zuul.GearmanCleanup")

    def __init__(self, gearman):
        threading.Thread.__init__(self)
        self.daemon = True
        self.gearman = gearman
        self.wake_event = threading.Event()
        self._stopped = False

    def stop(self):
        self._stopped = True
        self.wake_event.set()

    def run(self):
        while True:
            self.wake_event.wait(300)
            if self._stopped:
                return
            try:
                self.gearman.lookForLostBuilds()
            except Exception:
                self.log.exception("Exception checking builds:")


def getJobData(job):
    if not len(job.data):
        return {}
    d = job.data[-1]
    if not d:
        return {}
    return json.loads(d)


class ZuulGearmanClient(gear.Client):
    def __init__(self, zuul_gearman):
        super(ZuulGearmanClient, self).__init__('Zuul Executor Client')
        self.__zuul_gearman = zuul_gearman

    def handleWorkComplete(self, packet):
        job = super(ZuulGearmanClient, self).handleWorkComplete(packet)
        self.__zuul_gearman.onBuildCompleted(job)
        return job

    def handleWorkFail(self, packet):
        job = super(ZuulGearmanClient, self).handleWorkFail(packet)
        self.__zuul_gearman.onBuildCompleted(job)
        return job

    def handleWorkException(self, packet):
        job = super(ZuulGearmanClient, self).handleWorkException(packet)
        self.__zuul_gearman.onBuildCompleted(job)
        return job

    def handleWorkStatus(self, packet):
        job = super(ZuulGearmanClient, self).handleWorkStatus(packet)
        self.__zuul_gearman.onWorkStatus(job)
        return job

    def handleWorkData(self, packet):
        job = super(ZuulGearmanClient, self).handleWorkData(packet)
        self.__zuul_gearman.onWorkStatus(job)
        return job

    def handleDisconnect(self, job):
        job = super(ZuulGearmanClient, self).handleDisconnect(job)
        self.__zuul_gearman.onDisconnect(job)

    def handleStatusRes(self, packet):
        try:
            super(ZuulGearmanClient, self).handleStatusRes(packet)
        except gear.UnknownJobError:
            handle = packet.getArgument(0)
            for build in self.__zuul_gearman.builds.values():
                if build._gearman_job.handle == handle:
                    self.__zuul_gearman.onUnknownJob(build)


class ExecutorClient(object):
    log = logging.getLogger("zuul.ExecutorClient")

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        self.builds = {}
        self.meta_jobs = {}  # A list of meta-jobs like stop or describe

        self.result_events = PipelineResultEventQueue.createRegistry(
            self.sched.zk_client
        )

        server = config.get('gearman', 'server')
        port = get_default(self.config, 'gearman', 'port', 4730)
        ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        self.gearman = ZuulGearmanClient(self)
        self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca,
                               keepalive=True, tcp_keepidle=60,
                               tcp_keepintvl=30, tcp_keepcnt=5)

        self.cleanup_thread = GearmanCleanup(self)
        self.cleanup_thread.start()

    def stop(self):
        self.log.debug("Stopping")
        self.cleanup_thread.stop()
        self.cleanup_thread.join()
        self.gearman.shutdown()
        self.log.debug("Stopped")

    def execute(self, job, item, pipeline, dependent_changes=[],
                merger_items=[]):
        log = get_annotated_logger(self.log, item.event)
        uuid = str(uuid4().hex)
        nodeset = item.current_build_set.getJobNodeSet(job.name)
        log.info(
            "Execute job %s (uuid: %s) on nodes %s for change %s "
            "with dependent changes %s",
            job, uuid, nodeset, item.change, dependent_changes)

        params = zuul.executor.common.construct_gearman_params(
            uuid, self.sched, nodeset,
            job, item, pipeline, dependent_changes, merger_items,
            redact_secrets_and_keys=False)
        # TODO: deprecate and remove this variable?
        params["zuul"]["_inheritance_path"] = list(job.inheritance_path)

        build = Build(
            job,
            item.current_build_set,
            uuid,
            zuul_event_id=item.event.zuul_event_id,
        )
        build.parameters = params
        build.nodeset = nodeset

        log.debug("Adding build %s of job %s to item %s",
                  build, job, item)
        item.addBuild(build)
        self.builds[uuid] = build

        if job.name == 'noop':
            data = {"start_time": time.time()}
            started_event = BuildStartedEvent(build.uuid, data)
            self.result_events[pipeline.tenant.name][pipeline.name].put(
                started_event
            )

            result = {"result": "SUCCESS", "end_time": time.time()}
            completed_event = BuildCompletedEvent(build.uuid, result)
            self.result_events[pipeline.tenant.name][pipeline.name].put(
                completed_event
            )

            return build

        # Update zuul attempts after addBuild above to ensure build_set
        # is up to date.
        attempts = build.build_set.getTries(job.name)
        params["zuul"]['attempts'] = attempts

        functions = getGearmanFunctions(self.gearman)
        function_name = 'executor:execute'
        # Because all nodes belong to the same provider, region and
        # availability zone we can get executor_zone from only the first
        # node.
        executor_zone = None
        if params["nodes"] and params["nodes"][0].get('attributes'):
            executor_zone = params[
                "nodes"][0]['attributes'].get('executor-zone')

        if executor_zone:
            _fname = '%s:%s' % (
                function_name,
                executor_zone)
            if _fname in functions:
                function_name = _fname
            else:
                self.log.warning(
                    "Job requested '%s' zuul-executor zone, but no "
                    "zuul-executors found for this zone; ignoring zone "
                    "request" % executor_zone)

        gearman_job = gear.TextJob(
            function_name, json_dumps(params), unique=uuid)

        build._gearman_job = gearman_job
        build.__gearman_worker = None

        if pipeline.precedence == PRECEDENCE_NORMAL:
            precedence = gear.PRECEDENCE_NORMAL
        elif pipeline.precedence == PRECEDENCE_HIGH:
            precedence = gear.PRECEDENCE_HIGH
        elif pipeline.precedence == PRECEDENCE_LOW:
            precedence = gear.PRECEDENCE_LOW

        try:
            self.gearman.submitJob(gearman_job, precedence=precedence,
                                   timeout=300)
        except Exception:
            log.exception("Unable to submit job to Gearman")
            # TODO (felix): Directly put the result event in the queue
            self.onBuildCompleted(gearman_job, 'EXCEPTION')
            return build

        if not gearman_job.handle:
            log.error("No job handle was received for %s after"
                      " 300 seconds; marking as lost.",
                      gearman_job)
            # TODO (felix): Directly put the result event in the queue
            self.onBuildCompleted(gearman_job, 'NO_HANDLE')

        log.debug("Received handle %s for %s", gearman_job.handle, build)

        return build

    def cancel(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        # Returns whether a running build was canceled
        log.info("Cancel build %s for job %s", build, build.job)

        build.canceled = True
        try:
            job = build._gearman_job  # noqa
        except AttributeError:
            log.debug("Build has no associated gearman job")
            return False

        if build.__gearman_worker is not None:
            log.debug("Build has already started")
            self.cancelRunningBuild(build)
            log.debug("Canceled running build")
            return True
        else:
            log.debug("Build has not started yet")

        log.debug("Looking for build in queue")
        if self.cancelJobInQueue(build):
            log.debug("Removed build from queue")
            return False

        time.sleep(1)

        log.debug("Still unable to find build to cancel")
        if build.__gearman_worker is not None:
            log.debug("Build has just started")
            self.cancelRunningBuild(build)
            log.debug("Canceled running build")
            return True
        log.error("Unable to cancel build")

    def onBuildCompleted(self, job, result=None):
        if job.unique in self.meta_jobs:
            del self.meta_jobs[job.unique]
            return

    # TODO (felix): Remove this once the builds are executed via ZooKeeper.
    # It's currently necessary to set the correct private attribute on the
    # build for the gearman worker.
    def setWorkerInfo(self, build, data):
        # Update information about worker
        build.worker.updateFromData(data)
        build.__gearman_worker = build.worker.name

    def onWorkStatus(self, job):
        data = getJobData(job)
        self.log.debug("Build %s update %s" % (job, data))

    def onDisconnect(self, job):
        self.log.info("Gearman job %s lost due to disconnect" % job)
        self.onBuildCompleted(job, 'DISCONNECT')

        build = self.builds.get(job.unique)
        if build:
            tenant_name = build.build_set.item.pipeline.tenant.name
            pipeline_name = build.build_set.item.pipeline.name
            result = {"result": "DISCONNECT", "end_time": time.time()}
            event = BuildCompletedEvent(build.uuid, result)
            self.result_events[tenant_name][pipeline_name].put(event)

    def onUnknownJob(self, build):
        self.log.info("Gearman job for build %s lost "
                      "due to unknown handle" % build)
        # We don't need to call onBuildCompleted, because by
        # definition, we have no record of the job.
        tenant_name = build.build_set.item.pipeline.tenant.name
        pipeline_name = build.build_set.item.pipeline.name
        result = {"result": "LOST", "end_time": time.time()}
        event = BuildCompletedEvent(build.uuid, result)
        self.result_events[tenant_name][pipeline_name].put(event)

    def cancelJobInQueue(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        job = build._gearman_job

        req = gear.CancelJobAdminRequest(job.handle)
        job.connection.sendAdminRequest(req, timeout=300)
        log.debug("Response to cancel build request: %s", req.response.strip())
        if req.response.startswith(b"OK"):
            # Since this isn't otherwise going to get a build complete
            # event, send one to the scheduler so that it can unlock
            # the nodes.
            tenant_name = build.build_set.item.pipeline.tenant.name
            pipeline_name = build.build_set.item.pipeline.name

            result = {"result": "CANCELED", "end_time": time.time()}
            event = BuildCompletedEvent(build.uuid, result)
            self.result_events[tenant_name][pipeline_name].put(event)
            return True
        return False

    def cancelRunningBuild(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id)
        if not build.__gearman_worker:
            log.error("Build %s has no manager while canceling", build)
        stop_uuid = str(uuid4().hex)
        data = dict(uuid=build._gearman_job.unique,
                    zuul_event_id=build.zuul_event_id)
        stop_job = gear.TextJob("executor:stop:%s" % build.__gearman_worker,
                                json_dumps(data), unique=stop_uuid)
        self.meta_jobs[stop_uuid] = stop_job
        log.debug("Submitting stop job: %s", stop_job)
        self.gearman.submitJob(stop_job, precedence=gear.PRECEDENCE_HIGH,
                               timeout=300)
        return True

    def resumeBuild(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id)
        if not build.__gearman_worker:
            log.error("Build %s has no manager while resuming", build)
        resume_uuid = str(uuid4().hex)
        data = dict(uuid=build._gearman_job.unique,
                    zuul_event_id=build.zuul_event_id)
        stop_job = gear.TextJob("executor:resume:%s" % build.__gearman_worker,
                                json_dumps(data), unique=resume_uuid)
        self.meta_jobs[resume_uuid] = stop_job
        log.debug("Submitting resume job: %s", stop_job)
        self.gearman.submitJob(stop_job, precedence=gear.PRECEDENCE_HIGH,
                               timeout=300)

    def lookForLostBuilds(self):
        self.log.debug("Looking for lost builds")
        # Construct a list from the values iterator to protect from it changing
        # out from underneath us.
        for build in list(self.builds.values()):
            if build.result:
                # The build has finished, it will be removed
                continue
            job = build._gearman_job
            if not job.handle:
                # The build hasn't been enqueued yet
                continue
            p = gear.Packet(gear.constants.REQ, gear.constants.GET_STATUS,
                            job.handle)
            job.connection.sendPacket(p)
