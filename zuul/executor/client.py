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
from typing import Dict, List, Optional

import logging
import os
import threading
from typing import Set
from uuid import uuid4

from kazoo.recipe.cache import TreeEvent

from zuul.lib.logutil import get_annotated_logger
from zuul.model import Build, Job, Pipeline, Project, QueueItem, PRIORITY_MAP
from zuul.source import BaseSource
from zuul.zk import ZooKeeper
from zuul.zk.cache import ZooKeeperBuildItem


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


class ExecutorClient(object):
    log = logging.getLogger("zuul.ExecutorClient")

    def __init__(self, config, sched, zk: ZooKeeper):
        self.config = config
        self.sched = sched
        self.zk: ZooKeeper = zk
        self.builds: Dict[str, Build] = {}

        self.cleanup_thread = GearmanCleanup(self)
        self.cleanup_thread.start()
        self.zk.builds.register_cache_listener(self.__tree_cache_listener)

    def __str__(self):
        return "<ExecutorClient id=%s>" % hex(hash(self))

    def stop(self):
        self.log.debug("Stopping")
        self.cleanup_thread.stop()
        self.cleanup_thread.join()
        self.log.debug("Stopped")

    def __tree_cache_listener(self, segments: List[str], event: TreeEvent,
                              item: Optional[ZooKeeperBuildItem]) -> None:

        if event.event_type in (TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED)\
                and item:
            self.log.debug("TreeEvent (%s) [%s]: %s", event, segments, item)
            if len(segments) == 2 and segments[1] == 'data':
                self.onWorkStatus(item)
            elif len(segments) == 2 and segments[1] == 'status':
                self.onWorkStatus(item)
            elif len(segments) == 2 and segments[1] == 'result':
                self.onBuildCompleted(item)
            elif len(segments) == 2 and segments[1] == 'exception':
                self.onBuildCompleted(item)

    def execute(self, job: Job, item: QueueItem, pipeline: Pipeline,
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

        zuul_params = dict(
            build=uuid,
            buildset=item.current_build_set.uuid,
            ref=item.change.ref,
            pipeline=pipeline.name,
            job=job.name,
            voting=job.voting,
            project=project,
            tenant=tenant.name,
            timeout=job.timeout,
            event_id=item.event.zuul_event_id if item.event else None,
            jobtags=sorted(job.tags),
            _inheritance_path=list(job.inheritance_path))
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
        params['vars'] = job.variables
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
        params['zuul_event_id'] = item.event.zuul_event_id\
            if item.event else None
        build = Build(job, uuid, zuul_event_id=item.event
                      .zuul_event_id if item.event else None)
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

        # Because all nodes belong to the same provider, region and
        # availability zone we can get executor_zone from only the first
        # node.
        executor_zone = None
        if nodes and nodes[0].get('attributes'):
            executor_zone = nodes[0]['attributes'].get('executor-zone')
        self.zk.builds.register_zone(executor_zone)

        self.builds[uuid] = build

        build.zookeeper_node = self.zk.builds.submit(
            uuid=uuid, params=params, zone=executor_zone,
            precedence=PRIORITY_MAP[pipeline.precedence])
        return build

    def cancel(self, build):
        log = get_annotated_logger(self.log, build.zuul_event_id,
                                   build=build.uuid)
        # Returns whether a running build was canceled
        log.info("Cancel build %s for job %s", build, build.job)

        build.canceled = True

        if build.zookeeper_node is not None:
            log.debug("Canceling build: %s", build.zookeeper_node)
            if build.zookeeper_node:
                lock = self.zk.builds.get_lock(build.zookeeper_node)
                if lock.acquire(blocking=False):
                    try:
                        self.zk.builds.remove(build.zookeeper_node)
                        build.zookeeper_node = None
                        try:
                            del self.builds[build.uuid]
                        except KeyError:
                            pass
                        self.sched.onBuildCompleted(build, 'CANCELED', {}, [])
                    finally:
                        lock.release()
                else:
                    self.zk.builds.cancel_request(build.zookeeper_node)

            log.debug("Canceled build")
            return True
        else:
            log.debug("Build has not been submitted")
            return False

    def onBuildCompleted(self, build_item: ZooKeeperBuildItem, result=None):
        build = self.builds.get(build_item.content['uuid'])
        if build:
            log = get_annotated_logger(self.log, build.zuul_event_id,
                                       build=build_item.content['uuid'])

            if not build.build_set:
                raise Exception("Build set undefined for %s" % build)

            build.node_labels = build_item.result.get('node_labels', [])
            build.node_name = build_item.result.get('node_name')
            if result is None:
                result = build_item.result.get('result')
                build.error_detail = build_item.result.get('error_detail')
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

            result_data = build_item.result.get('data', {})
            warnings = build_item.result.get('warnings', [])
            log.info("Build complete, result %s, warnings %s",
                     result, warnings)

            if build.retry:
                result = 'RETRY'

            # If the build was canceled, we did actively cancel the job so
            # don't overwrite the result and don't retry.
            if build.canceled:
                result = build.result
                build.retry = False

            if build.zookeeper_node:
                self.zk.builds.remove(build.zookeeper_node)
                build.zookeeper_node = None
            self.sched.onBuildCompleted(build, result, result_data, warnings)
            # The test suite expects the build to be removed from the
            # internal dict after it's added to the report queue.
            del self.builds[build_item.content['uuid']]
        elif not build_item.cancel:
            self.log.error("Unable to find build %s" %
                           build_item.content['uuid'])

    def onWorkStatus(self, build_item: ZooKeeperBuildItem):
        self.log.debug("Build %s update %s on %s", build_item.content,
                       build_item.data, self)
        build = self.builds.get(build_item.content['uuid'])
        if build:
            started = (build.url is not None)
            # Allow URL to be updated
            self.log.debug("Build %s url update: %s -> %s on %s", build,
                           build.url, build_item.data.get('url'), self)
            build.url = build_item.data.get('url', build.url)
            # Update information about worker
            build.worker.updateFromData(build_item.data)

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

    def resumeBuild(self, build: Build) -> bool:
        log = get_annotated_logger(self.log, build.zuul_event_id)
        log.debug("Resuming build: %s", build.zookeeper_node)
        if build.zookeeper_node:
            self.zk.builds.resume_request(build.zookeeper_node)
            return True
        return False
