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
from typing import Dict, Any, List, Optional

import json
import logging
import os
import time
import threading
from typing import Set
from uuid import uuid4

from kazoo.recipe.cache import TreeEvent

from zuul.lib.logutil import get_annotated_logger
from zuul.model import Build, Job, Pipeline, Project
from zuul.source import BaseSource
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperBuildTreeCacheClient


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


# def getJobData(job):
#     if not len(job.data):
#         return {}
#     d = job.data[-1]
#     if not d:
#         return {}
#     return json.loads(d)


# class ZuulGearmanClient(gear.Client):
#     def __init__(self, zuul_gearman):
#         super(ZuulGearmanClient, self).__init__('Zuul Executor Client')
#         self.__zuul_gearman = zuul_gearman
#
#     def handleWorkComplete(self, packet):
#         job = super(ZuulGearmanClient, self).handleWorkComplete(packet)
#         self.__zuul_gearman.onBuildCompleted(job)
#         return job
#
#     def handleWorkFail(self, packet):
#         job = super(ZuulGearmanClient, self).handleWorkFail(packet)
#         self.__zuul_gearman.onBuildCompleted(job)
#         return job
#
#     def handleWorkException(self, packet):
#         job = super(ZuulGearmanClient, self).handleWorkException(packet)
#         self.__zuul_gearman.onBuildCompleted(job)
#         return job
#
#     def handleWorkStatus(self, packet):
#         job = super(ZuulGearmanClient, self).handleWorkStatus(packet)
#         self.__zuul_gearman.onWorkStatus(job)
#         return job
#
#     def handleWorkData(self, packet):
#         job = super(ZuulGearmanClient, self).handleWorkData(packet)
#         self.__zuul_gearman.onWorkStatus(job)
#         return job
#
#     def handleDisconnect(self, job):
#         job = super(ZuulGearmanClient, self).handleDisconnect(job)
#         self.__zuul_gearman.onDisconnect(job)
#
#     def handleStatusRes(self, packet):
#         try:
#             job = super(ZuulGearmanClient, self).handleStatusRes(packet)
#         except gear.UnknownJobError:
#             handle = packet.getArgument(0)
#             for build in self.__zuul_gearman.builds.values():
#                 if build.__gearman_job.handle == handle:
#                     # NOTE JK: Whether unreachable code, fails or job always
#                     # None
#                     self.__zuul_gearman.onUnknownJob(job)


class ZuulZookeeperJobHandler(object):
    def __init__(self, log):
        self.log = log

    def __call__(self, uuid: str, data: Dict[str, Any]):
        self.log.debug("Job %s: %s" % (uuid, json.dumps(data)))


class ExecutorClient(ZooKeeperBuildTreeCacheClient):
    log = logging.getLogger("zuul.ExecutorClient")

    def __init__(self, config, sched, zk):
        super().__init__(zk=zk, root=zk.ZUUL_BUILDS_ROOT)
        self.config = config
        self.sched = sched
        self.zk = zk
        self.builds = {}  # type: Dict[str, Build]
        self.meta_jobs = {}  # A list of meta-jobs like stop or describe

        # server = config.get('gearman', 'server')
        # port = get_default(self.config, 'gearman', 'port', 4730)
        # ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        # ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        # ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
        # self.gearman = ZuulGearmanClient(self)
        # self.gearman.addServer(server, port, ssl_key, ssl_cert, ssl_ca,
        #                        keepalive=True, tcp_keepidle=60,
        #                        tcp_keepintvl=30, tcp_keepcnt=5)

        self.cleanup_thread = GearmanCleanup(self)
        self.cleanup_thread.start()
        self.start()

    def stop(self):
        self.log.debug("Stopping")
        super().stop()
        self.cleanup_thread.stop()
        self.cleanup_thread.join()
        # self.gearman.shutdown()
        self.log.debug("Stopped")

    def _tree_cache_listener(self, segments: List[str], event: TreeEvent,
                             old: Optional[ZooKeeperBuildItem],
                             new: Optional[ZooKeeperBuildItem]) -> None:

        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED)\
                and new:
            if len(segments) == 2 and segments[1] == 'data':
                self.onWorkStatus(new)
            elif len(segments) == 2 and segments[1] == 'status':
                self.onWorkStatus(new)
            elif len(segments) == 2 and segments[1] == 'result':
                self.onBuildCompleted(new)
            elif len(segments) == 2 and segments[1] == 'exception':
                self.onBuildCompleted(new)

    def execute(self, job: Job, item, pipeline: Pipeline,
                dependent_changes=None, merger_items=None):
        log = get_annotated_logger(self.log, item.event)
        tenant = pipeline.tenant
        uuid = str(uuid4().hex)
        nodeset = item.current_build_set.getJobNodeSet(job.name)
        log.info(
            "Execute job %s (uuid: %s) on nodes %s for change %s "
            "with dependent changes %s",
            job, uuid, nodeset, item.change, dependent_changes)

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
                           event_id=item.event.zuul_event_id,
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
        if (hasattr(item.change, 'oldrev')
                and item.change.oldrev
                and item.change.oldrev != '0' * 40):
            zuul_params['oldrev'] = item.change.oldrev
        if (hasattr(item.change, 'newrev')
                and item.change.newrev
                and item.change.newrev != '0' * 40):
            zuul_params['newrev'] = item.change.newrev
        zuul_params['projects'] = {}  # Set below
        zuul_params['items'] = dependent_changes or []
        zuul_params['child_jobs'] = list(item.job_graph.getDirectDependentJobs(
            job.name))

        params = dict()
        params['job'] = job.name
        params['timeout'] = job.timeout
        params['post_timeout'] = job.post_timeout
        params['items'] = merger_items or []
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
            d = playbook.toDict()
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
            params['ssh_keys'].append(dict(
                name='%s project key' % item.change.project.canonical_name,
                key=item.change.project.private_ssh_key))
        params['vars'] = job.variables
        params['extra_vars'] = job.extra_variables
        params['host_vars'] = job.host_variables
        params['group_vars'] = job.group_variables
        params['zuul'] = zuul_params
        projects = set()  # type: Set[Project]
        required_projects = set()  # type: Set[Project]

        def make_project_dict(proj: Project, override_branch=None,
                              override_checkout=None):
            project_metadata = item.layout.getProjectMetadata(
                proj.canonical_name)
            if project_metadata:
                project_default_branch = project_metadata.default_branch
            else:
                project_default_branch = 'master'
            connection = proj.source.connection
            return dict(connection=connection.connection_name,
                        name=proj.name,
                        canonical_name=proj.canonical_name,
                        override_branch=override_branch,
                        override_checkout=override_checkout,
                        default_branch=project_default_branch)

        if job.required_projects:
            for job_project in job.required_projects.values():
                (trusted, tenant_project) = tenant.getProject(
                    job_project.project_name)
                if tenant_project is None:
                    raise Exception("Unknown project %s" %
                                    (job_project.project_name,))
                params['projects'].append(
                    make_project_dict(tenant_project,
                                      job_project.override_branch,
                                      job_project.override_checkout))
                projects.add(tenant_project)
                required_projects.add(tenant_project)
        for change in (dependent_changes or []):
            # We have to find the project this way because it may not
            # be registered in the tenant (ie, a foreign project).
            source = self.sched.connections.getSourceByCanonicalHostname(
                change['project']['canonical_hostname']
            )  # type: Optional[BaseSource]
            if not source:
                raise Exception("Missing source!")
            source_project = source.getProject(change['project']['name'])
            if source_project not in projects:
                params['projects'].append(make_project_dict(source_project))
                projects.add(source_project)  # noqa
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
        params['zuul_event_id'] = item.event.zuul_event_id
        build = Build(job, uuid, zuul_event_id=item.event.zuul_event_id)
        build.parameters = params
        build.nodeset = nodeset

        log.debug("Adding build %s of job %s to item %s",
                  build, job, item)
        item.addBuild(build)

        if job.name == 'noop':
            self.sched.onBuildStarted(build)
            self.sched.onBuildCompleted(build, 'SUCCESS', {}, [])
            return build

        # Update zuul attempts after addBuild above to ensure build_set
        # is up to date.
        if not build.build_set:
            raise Exception("Build set undefined for %s" % build)
        attempts = build.build_set.getTries(job.name)
        zuul_params['attempts'] = attempts

        # functions = getGearmanFunctions(self.gearman)
        # function_name = 'executor:execute'
        # # Because all nodes belong to the same provider, region and
        # # availability zone we can get executor_zone from only the first
        # # node.
        # executor_zone = None
        # if nodes and nodes[0].get('attributes'):
        #     executor_zone = nodes[0]['attributes'].get('executor-zone')
        #
        # if executor_zone:
        #     _fname = '%s:%s' % (
        #         function_name,
        #         executor_zone)
        #     if _fname in functions:
        #         function_name = _fname
        #     else:
        #         self.log.warning(
        #             "Job requested '%s' zuul-executor zone, but no "
        #             "zuul-executors found for this zone; ignoring zone "
        #             "request" % executor_zone)

        # gearman_job = gear.TextJob(
        #     function_name, json_dumps(params), unique=uuid)

        # build.__gearman_job = gearman_job
        # build.__gearman_worker = None
        self.builds[uuid] = build

        # if pipeline.precedence == zuul.model.PRECEDENCE_NORMAL:
        #     precedence = gear.PRECEDENCE_NORMAL
        # elif pipeline.precedence == zuul.model.PRECEDENCE_HIGH:
        #     precedence = gear.PRECEDENCE_HIGH
        # elif pipeline.precedence == zuul.model.PRECEDENCE_LOW:
        #     precedence = gear.PRECEDENCE_LOW

        try:
            # self.gearman.submitJob(gearman_job, precedence=precedence,
            #                        timeout=300)
            build.zookeeper_node = self._zk.submitBuild(
                uuid, params, precedence=pipeline.precedence,
                watcher=ZuulZookeeperJobHandler(self.log))
        except Exception:
            # TODO: Handle correctly
            log.exception("Unable to submit job")
            # self.onBuildCompleted(gearman_job, 'EXCEPTION')
            # return build

        # TODO: Check if still needed
        # if not gearman_job.handle:
        #     log.error("No job handle was received for %s after"
        #               " 300 seconds; marking as lost.",
        #               gearman_job)
        #     self.onBuildCompleted(gearman_job, 'NO_HANDLE')
        #
        # log.debug("Received handle %s for %s", gearman_job.handle, build)
        #
        return build

    def cancel(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        # Returns whether a running build was canceled
        log.info("Cancel build %s for job %s", build, build.job)

        build.canceled = True
        try:
            job = build.__gearman_job  # noqa
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
        return False

    def onBuildCompleted(self, build_item: ZooKeeperBuildItem, result=None):
        # if job.unique in self.meta_jobs:
        #     del self.meta_jobs[job.unique]
        #     return

        build = self.builds.get(build_item.content['uuid'])
        if build:
            log = get_annotated_logger(self.log, build.zuul_event_id,
                                       build=build_item.content['uuid'])

            if not build.build_set:
                raise Exception("Build set undefined for %s" % build)

            build.node_labels = build_item.data.get('node_labels', [])
            build.node_name = build_item.data.get('node_name')
            if result is None:
                result = build_item.data.get('result')
                build.error_detail = build_item.data.get('error_detail')
            if result is None:
                if (build.build_set.getTries(build.job.name) >=
                        build.job.attempts):
                    result = 'RETRY_LIMIT'
                else:
                    build.retry = True
            if result in ('DISCONNECT', 'ABORTED'):
                # Always retry if the executor just went away
                build.retry = True
            if result == 'MERGER_FAILURE':
                # The build result MERGER_FAILURE is a bit misleading here
                # because when we got here we know that there are no merge
                # conflicts. Instead this is most likely caused by some
                # infrastructure failure. This can be anything like connection
                # issue, drive corruption, full disk, corrupted git cache, etc.
                # This may or may not be a recoverable failure so we should
                # retry here respecting the max retries. But to be able to
                # distinguish from RETRY_LIMIT which normally indicates pre
                # playbook failures we keep the build result after the max
                # attempts.
                if (build.build_set.getTries(build.job.name) <
                        build.job.attempts):
                    build.retry = True

            result_data = build_item.data.get('data', {})
            warnings = build_item.data.get('warnings', [])
            log.info("Build complete, result %s, warnings %s",
                     result, warnings)

            if build.retry:
                result = 'RETRY'

            # If the build was canceled, we did actively cancel the job so
            # don't overwrite the result and don't retry.
            if build.canceled:
                result = build.result
                build.retry = False

            self.sched.onBuildCompleted(build, result, result_data, warnings)
            # The test suite expects the build to be removed from the
            # internal dict after it's added to the report queue.
            del self.builds[build_item.content['uuid']]
        else:
            # FIXME JK: need to distinguish between complete and explicit stop
            # if not job.name.startswith("executor:stop:"):
            self.log.error("Unable to find build %s" %
                           build_item.content['uuid'])

    def onWorkStatus(self, build_item: ZooKeeperBuildItem):
        self.log.debug("Build %s update %s" % (build_item.content,
                                               build_item.data))
        build = self.builds.get(build_item.content['uuid'])
        if build:
            started = (build.url is not None)
            # Allow URL to be updated
            build.url = build_item.data.get('url', build.url)
            # Update information about worker
            build.worker.updateFromData(build_item.data)
            # build.__gearman_worker = build.worker.name

            if 'paused' in build_item.data and\
                    build.paused != build_item.data['paused']:
                build.paused = build_item.data['paused']
                if build.paused:
                    result_data = build_item.data.get('data', {})
                    self.sched.onBuildPaused(build, result_data)

            if not started:
                self.log.info("Build %s started" % build_item.content)
                self.sched.onBuildStarted(build)
        else:
            self.log.error("Unable to find build %s" %
                           build_item.content['uuid'])

    # def onDisconnect(self, job):
    #     self.log.info("Gearman job %s lost due to disconnect" % job)
    #     self.onBuildCompleted(job, 'DISCONNECT')

    # def onUnknownJob(self, job):
    #     self.log.info("Gearman job %s lost due to unknown handle" % job)
    #     self.onBuildCompleted(job, 'LOST')

    # TODO JK
    def cancelJobInQueue(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        if build.zookeeper_node:
            self._zk.cancelBuildInQueue(build.zookeeper_node)
            self.sched.onBuildCompleted(build, 'CANCELED', {}, [])
            return True
        return False

        # job = build.__gearman_job
        #
        # req = gear.CancelJobAdminRequest(job.handle)
        # job.connection.sendAdminRequest(req, timeout=300)
        # log.debug("Response to cancel build request: %s",
        #           req.response.strip())
        # if req.response.startswith(b"OK"):
        #     try:
        #         del self.builds[job.unique]
        #     except Exception:
        #         pass
        #     # Since this isn't otherwise going to get a build complete
        #     # event, send one to the scheduler so that it can unlock
        #     # the nodes.
        #     self.sched.onBuildCompleted(build, 'CANCELED', {}, [])
        #     return True
        # return False
        raise Exception("Not implemented")

    def cancelRunningBuild(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id)
        # if not build.__gearman_worker:
        #     log.error("Build %s has no manager while canceling", build)
        # stop_uuid = str(uuid4().hex)
        # data = dict(uuid=build.__gearman_job.unique,
        #             zuul_event_id=build.zuul_event_id)
        # stop_job = gear.TextJob("executor:stop:%s" % build.__gearman_worker,
        #                         json_dumps(data), unique=stop_uuid)
        # self.meta_jobs[stop_uuid] = stop_job
        # log.debug("Submitting stop job: %s", stop_job)
        log.debug("Canceling build: %s", build.zookeeper_node)
        # self.gearman.submitJob(stop_job, precedence=gear.PRECEDENCE_HIGH,
        #                        timeout=300)
        if build.zookeeper_node:
            self._zk.cancelBuildRequest(build.zookeeper_node)
            return True
        return False

    def resumeBuild(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id)
        # if not build.__gearman_worker:
        #     log.error("Build %s has no manager while resuming", build)
        # resume_uuid = str(uuid4().hex)
        # data = dict(uuid=build.__gearman_job.unique,
        #             zuul_event_id=build.zuul_event_id)
        # stop_job = gear.TextJob("executor:resume:%s" %
        #                         build.__gearman_worker,
        #                         json_dumps(data), unique=resume_uuid)
        # self.meta_jobs[resume_uuid] = stop_job
        # log.debug("Submitting resume job: %s", stop_job)
        log.debug("Resuming build: %s", build.zookeeper_node)
        # self.gearman.submitJob(stop_job, precedence=gear.PRECEDENCE_HIGH,
        #                        timeout=300)
        if build.zookeeper_node:
            self._zk.resumeBuildRequest(build.zookeeper_node)
            return True
        return False

    # TODO JK
    def lookForLostBuilds(self) -> None:
        self.log.debug("Looking for lost builds")
        # Construct a list from the values iterator to protect from it changing
        # out from underneath us.
        # for build in list(self.builds.values()):
        #     if build.result:
        #         # The build has finished, it will be removed
        #         continue
        #     job = build.__gearman_job
        #     if not job.handle:
        #         # The build hasn't been enqueued yet
        #         continue
        #     p = gear.Packet(gear.constants.REQ, gear.constants.GET_STATUS,
        #                     job.handle)
        #     job.connection.sendPacket(p)
