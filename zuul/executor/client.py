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

import logging
from uuid import uuid4

import zuul.executor.common
from zuul.lib.logutil import get_annotated_logger
from zuul.model import (
    Build,
    BuildCompletedEvent,
    BuildRequestState,
    BuildStartedEvent,
    PRIORITY_MAP,
)
from zuul.zk.event_queues import PipelineResultEventQueue
from zuul.zk.executor import ExecutorApi


class ExecutorClient(object):
    log = logging.getLogger("zuul.ExecutorClient")
    _executor_api_class = ExecutorApi

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        self.builds = {}
        self.meta_jobs = {}  # A list of meta-jobs like stop or describe

        self.executor_api = self._executor_api_class(self.sched.zk_client)
        self.result_events = PipelineResultEventQueue.createRegistry(
            self.sched.zk_client
        )

    def stop(self):
        self.log.debug("Stopping")

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

        self.builds[uuid] = build

        if job.name == 'noop':
            started_event = BuildStartedEvent(build.uuid, None)
            self.result_events[pipeline.tenant.name][pipeline.name].put(
                started_event
            )

            result = {"result": "SUCCESS"}
            completed_event = BuildCompletedEvent(build.uuid, result)
            self.result_events[pipeline.tenant.name][pipeline.name].put(
                completed_event
            )

            return

        # Update zuul attempts after addBuild above to ensure build_set
        # is up to date.
        attempts = build.build_set.getTries(job.name)
        params["zuul"]['attempts'] = attempts

        # Because all nodes belong to the same provider, region and
        # availability zone we can get executor_zone from only the first
        # node.
        executor_zone = None
        if params["nodes"] and params["nodes"][0].get('attributes'):
            executor_zone = params[
                "nodes"][0]['attributes'].get('executor-zone')

        zone_known = False
        if executor_zone:
            # Check the component registry for executors subscribed to this
            # zone
            # TODO (felix): This is not very efficient in its current state as
            # we are querying ZooKeeper for every build request to get the list
            # of components. To improve this, we could implement a cache in the
            # component registry, so it would be sufficient to iterate over
            # local dictionaries instead.
            for comp in self.sched.component_registry.all(kind="executor"):
                if comp.zone == executor_zone:
                    zone_known = True
                    break

        if not zone_known:
            self.log.warning(
                "Job requested '%s' zuul-executor zone, but no zuul-executors "
                "found for this zone; ignoring zone request", executor_zone)
            # Fall back to the default zone
            executor_zone = ExecutorApi.DEFAULT_ZONE

        build.build_request_ref = self.executor_api.submit(
            uuid=uuid,
            tenant_name=build.build_set.item.pipeline.tenant.name,
            pipeline_name=build.build_set.item.pipeline.name,
            params=params,
            zone=executor_zone,
            precedence=PRIORITY_MAP[pipeline.precedence],
        )

    def cancel(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        # Returns whether a running build was canceled
        log.info("Cancel build %s for job %s", build, build.job)

        build.canceled = True

        if not build.build_request_ref:
            log.debug("Build has not been submitted to ZooKeeper")
            return False

        build_request = self.executor_api.get(build.build_request_ref)
        if build_request:
            log.debug("Canceling build request %s", build_request)
            # If we can acquire the build request lock here, the build wasn't
            # picked up by any executor server yet. With acquiring the lock
            # we prevent the executor server from picking up the build so we
            # can cancel it before it will run.
            if self.executor_api.lock(build_request, blocking=False):
                log.debug(
                    "Canceling build %s directly because it is not locked by "
                    "any executor",
                    build_request,
                )
                # Mark the build request as complete and forward the event to
                # the scheduler, so the executor server doesn't pick up the
                # request. The build will be deleted from the scheduler when it
                # picks up the BuildCompletedEvent.
                try:
                    build_request.state = BuildRequestState.COMPLETED
                    self.executor_api.update(build_request)

                    result = {"result": "CANCELED"}
                    tenant_name = build.build_set.item.pipeline.tenant.name
                    pipeline_name = build.build_set.item.pipeline.name
                    event = BuildCompletedEvent(build_request.uuid, result)
                    self.result_events[tenant_name][pipeline_name].put(event)
                finally:
                    self.executor_api.unlock(build_request)
            else:
                log.debug(
                    "Sending cancel request for build %s because it is locked",
                    build_request,
                )
                # If the build request is locked, schedule a cancel request in
                # the executor server.
                self.executor_api.requestCancel(build_request)

            log.debug("Canceled build")
            return True

        return False

    def resumeBuild(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id)

        if not build.build_request_ref:
            log.debug("Build has not been submitted")
            return False

        build_request = self.executor_api.get(build.build_request_ref)
        if build_request:
            log.debug("Requesting resume for build %s", build)
            self.executor_api.requestResume(build_request)
            return True
        return False

    def removeBuild(self, build: Build) -> None:
        log = get_annotated_logger(self.log, build.zuul_event_id)
        log.debug("Removing build %s", build.uuid)

        if not build.build_request_ref:
            log.debug("Build has not been submitted to ZooKeeper")
            return

        build_request = self.executor_api.get(build.build_request_ref)
        if build_request:
            self.executor_api.remove(build_request)

        del self.builds[build.uuid]
