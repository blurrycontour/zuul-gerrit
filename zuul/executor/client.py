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
import os
from uuid import uuid4

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
                           post_review=pipeline.post_review,
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
            source = self.sched.connections.getSourceByCanonicalHostname(
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
        else:
            params['zuul_event_id'] = None

        build = Build(
            job,
            item.current_build_set,
            uuid,
            zuul_event_id=params["zuul_event_id"],
        )
        build.parameters = params
        build.nodeset = nodeset

        log.debug("Adding build %s of job %s to item %s",
                  build, job, item)
        item.addBuild(build)

        self.builds[uuid] = build

        if job.name == 'noop':
            started_event = BuildStartedEvent(build.uuid, None)
            self.result_events[tenant.name][pipeline.name].put(started_event)

            result = {"result": "SUCCESS"}
            completed_event = BuildCompletedEvent(build.uuid, result)
            self.result_events[tenant.name][pipeline.name].put(completed_event)

            return

        # Update zuul attempts after addBuild above to ensure build_set
        # is up to date.
        attempts = build.build_set.getTries(job.name)
        zuul_params['attempts'] = attempts

        # Because all nodes belong to the same provider, region and
        # availability zone we can get executor_zone from only the first
        # node.
        executor_zone = None
        if nodes and nodes[0].get('attributes'):
            executor_zone = nodes[0]['attributes'].get('executor-zone')

        zone_known = False
        if executor_zone:
            # Check the component registry for executors subscribed to this
            # zone
            # TODO (felix): This is not very efficient in its current state as
            # we are querying ZooKeeper for every build request to get the list
            # of components. To improve this, we could implement a cache in the
            # component registry, so it would be sufficient to iterate over
            # local dictionaries instead.
            for comp in self.sched.component_registry.all(kind="executors"):
                if comp.get("zone") == executor_zone:
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
