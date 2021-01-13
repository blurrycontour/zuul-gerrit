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
from typing import Dict, Optional, Set
from uuid import uuid4

from zuul.lib.logutil import get_annotated_logger
from zuul.model import (
    Build,
    BuildCompletedEvent,
    BuildStartedEvent,
    Job,
    Pipeline,
    Project,
    QueueItem,
    PRIORITY_MAP,
)
from zuul.source import BaseSource
from zuul.zk import ZooKeeperClient
from zuul.zk.builds import BuildQueue, BuildResult, BuildState
from zuul.zk.event_queues import PipelineResultEventQueue


class ExecutorClient(object):
    log = logging.getLogger("zuul.ExecutorClient")

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched
        self.zk_client: ZooKeeperClient = self.sched.zk_client
        self.build_queue: BuildQueue = self.sched.build_queue
        self.builds: Dict[str, Build] = {}
        self.result_events = PipelineResultEventQueue.create_registry(
            self.zk_client
        )

    def stop(self):
        self.log.debug("Stopping")

    def execute(self, job: Job, item: QueueItem, pipeline: Pipeline,
                dependent_changes=None, merger_items=None) -> None:
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

        zuul_params = dict(
            build=uuid,
            buildset=item.current_build_set.uuid,
            ref=item.change.ref,
            pipeline=pipeline.name,
            post_review=pipeline.post_review,
            job=job.name,
            voting=job.voting,
            project=project,
            tenant=tenant.name,
            timeout=job.timeout,
            event_id=item.event.zuul_event_id if item.event else None,
            jobtags=sorted(job.tags),
            _inheritance_path=list(job.inheritance_path),
        )
        if job.artifact_data:
            zuul_params['artifacts'] = job.artifact_data
        if job.override_checkout:
            zuul_params['override_checkout'] = job.override_checkout
        if hasattr(item.change, 'branch'):
            zuul_params['branch'] = item.change.branch
        if hasattr(item.change, 'tag'):
            zuul_params['tag'] = getattr(item.change, 'tag')
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
        zuul_params['items'] = dependent_changes or []
        zuul_params['child_jobs'] = list(item.job_graph.getDirectDependentJobs(
            job.name)) if item.job_graph else []

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
        params['vars'] = job.combined_variables
        params['extra_vars'] = job.extra_variables
        params['host_vars'] = job.host_variables
        params['group_vars'] = job.group_variables
        params['zuul'] = zuul_params
        projects: Set[Project] = set()
        required_projects: Set[Project] = set()

        def make_project_dict(proj: Project, override_branch=None,
                              override_checkout=None):
            project_metadata = item.layout.getProjectMetadata(
                proj.canonical_name) if item.layout else None
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
            source: Optional[BaseSource] = self.sched.connections\
                .getSourceByCanonicalHostname(
                change['project']['canonical_hostname'])
            if not source:
                raise Exception("Missing source!")
            source_project = source.getProject(change['project']['name'])
            if source_project not in projects:
                params['projects'].append(make_project_dict(source_project))
                projects.add(source_project)
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
        params['zuul_event_id'] = item.event.zuul_event_id\
            if item.event else None

        build = Build(
            job,
            item.current_build_set,
            uuid,
            zuul_event_id=item.event.zuul_event_id if item.event else None
        )
        build.parameters = params
        build.nodeset = nodeset

        log.debug("Adding build %s of job %s to item %s",
                  build, job, item)
        item.addBuild(build)

        self.builds[uuid] = build

        if job.name == 'noop':
            # We don't store any noop builds in ZooKeper, so we have to fake
            # the build item path so that the scheduler can look up the build
            # object from the local executor client when receiving the result
            # events.
            fake_build_item_path = f"noop-{uuid}"
            started_event = BuildStartedEvent(fake_build_item_path)
            self.result_events[tenant.name][pipeline.name].put(started_event)
            build.result = "SUCCESS"
            completed_event = BuildCompletedEvent(fake_build_item_path)
            self.result_events[tenant.name][pipeline.name].put(completed_event)
            return

        # Update zuul attempts after addBuild above to ensure build_set
        # is up to date.
        attempts = build.build_set.getTries(job.name)
        zuul_params['attempts'] = attempts

        # Because all nodes belong to the same provider, region and
        # availability zone we can get executor_zone from only the first
        # node.
        executor_zone = self.build_queue.DEFAULT_ZONE
        if nodes and nodes[0].get('attributes'):
            executor_zone = nodes[0]['attributes'].get('executor-zone')

        build.zookeeper_node = self.build_queue.submit(
            uuid=uuid,
            tenant_name=build.build_set.item.pipeline.tenant.name,
            pipeline_name=build.build_set.item.pipeline.name,
            params=params,
            zone=executor_zone,
            precedence=PRIORITY_MAP[pipeline.precedence]
        )

    def cancel(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        # Returns whether a running build was canceled
        log.info("Cancel build %s for job %s", build, build.job)

        build.canceled = True

        if build.zookeeper_node is None:
            log.debug("Build has not been submitted")
            return False

        build_item = self.build_queue.get(build.zookeeper_node)
        if build_item:
            log.debug("Canceling build: %s", build_item.path)
            # If we can acquire the build lock here, this means that the build
            # didn't start on the executor server yet. With acquiring the lock
            # we prevent the executor server from picking up the build so we
            # can cancel it before it will run.
            # TODO (felix): With lock (context manager)
            if self.build_queue.lock(build_item, blocking=False):
                # Mark the build as complete and forward the event to the
                # scheduler, so the executor server doesn't pick up the build.
                # The build will be deleted from the scheduler when it picks
                # up the BuildCompletedEvent.
                try:
                    build_item.state = BuildState.COMPLETED
                    build_item.result = BuildResult.CANCELED
                    self.build_queue.update(build_item)

                    tenant_name = build.build_set.item.pipeline.tenant.name
                    pipeline_name = build.build_set.item.pipeline.name
                    event = BuildCompletedEvent(build_item.path)
                    self.result_events[tenant_name][pipeline_name].put(event)
                finally:
                    self.build_queue.unlock(build_item)
            else:
                # If the build is locked, schedule a cancel request in the
                # executor server.
                self.build_queue.request_cancel(build_item)

            log.debug("Canceled build")
            return True
        return False

    def resumeBuild(self, build: Build) -> bool:
        log = get_annotated_logger(
            self.log, event=build.zuul_event_id, build=build.uuid
        )

        if build.zookeeper_node is None:
            log.debug("Build has not been submitted")
            return False

        build_item = self.build_queue.get(build.zookeeper_node)
        if build_item:
            self.build_queue.request_resume(build_item)
            return True
        return False
