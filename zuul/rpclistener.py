# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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
import time
import traceback
from abc import ABCMeta
from typing import List, Optional, TYPE_CHECKING, Callable, Dict

from zuul import model
from zuul.connection import BaseConnection
from zuul.lib import encryption
from zuul.lib.jsonutil import ZuulJSONEncoder
from zuul.model import Build
from zuul.zk import ZooKeeperClient
from zuul.zk.cache import ZooKeeperWorkItem
from zuul.zk.work import ZooKeeperWork

if TYPE_CHECKING:
    from zuul.scheduler import Scheduler


class RPCListenerBase(metaclass=ABCMeta):
    log = logging.getLogger("zuul.RPCListenerBase")
    thread_name = 'zuul-rpc-gearman-worker'
    functions: List[str] = []

    def __init__(self, config, sched):
        self.config = config
        self.sched: Scheduler = sched
        self.zk_client: ZooKeeperClient = self.sched.zk_client
        self.zk_work: ZooKeeperWork = self.sched.zk_work
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        self.jobs: Dict[str, Callable[[ZooKeeperWorkItem], None]] = {}

        for func in self.functions:
            f = getattr(self, 'handle_%s' % func)
            self.jobs['zuul:%s' % func] = f

    def start(self):
        self._running = True
        if not self._thread:
            self._thread = threading.Thread(name=self.thread_name,
                                            target=self._run)
            self._thread.daemon = True
            self._thread.start()

    def stop(self):
        self._running = False

    def join(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def _run(self):
        while self._running:
            next_item = self.zk_work.next(self.jobs.keys())
            if next_item:
                try:
                    self.log.debug("Next executed job: %s", next_item)
                    self.jobs[next_item.name](next_item)
                except Exception:
                    self.log.exception('Exception while running job %s',
                                       next_item.name)
                    self.zk_work.complete(
                        next_item.path, traceback.format_exc(),
                        success=False)
            time.sleep(1.0)


class RPCListenerSlow(RPCListenerBase):
    log = logging.getLogger("zuul.RPCListenerSlow")
    thread_name = 'zuul-rpc-slow-gearman-worker'
    functions = [
        'dequeue',
        'enqueue',
        'enqueue_ref',
        'promote',
    ]

    def handle_dequeue(self, work_item: ZooKeeperWorkItem):
        tenant_name = work_item.content['params']['tenant']
        pipeline_name = work_item.content['params']['pipeline']
        project_name = work_item.content['params']['project']
        change = work_item.content['params']['change']
        ref = work_item.content['params']['ref']
        try:
            self.sched.dequeue(
                tenant_name, pipeline_name, project_name, change, ref)
        except Exception as e:
            self.zk_work.complete(work_item.path, str(e), success=False)
            return
        self.zk_work.complete(work_item.path)

    def _common_enqueue(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        event = model.TriggerEvent()
        event.timestamp = time.time()
        errors = ''
        project = None

        tenant = self.sched.abide.tenants.get(args['tenant'])
        if tenant and tenant.layout:
            event.tenant_name = args['tenant']

            (trusted, project) = tenant.getProject(args['project'])
            if project:
                event.project_hostname = project.canonical_hostname
                event.project_name = project.name
            else:
                errors += 'Invalid project: %s\n' % (args['project'],)

            pipeline = tenant.layout.pipelines.get(args['pipeline'])
            if pipeline:
                event.forced_pipeline = args['pipeline']
            else:
                errors += 'Invalid pipeline: %s\n' % (args['pipeline'],)
        else:
            errors += 'Invalid tenant: %s\n' % (args['tenant'],)

        return (args, event, errors, project)

    def handle_enqueue(self, work_item: ZooKeeperWorkItem):
        (args, event, errors, project) = self._common_enqueue(work_item)

        if not errors:
            event.change_number, event.patch_number = args['change'].split(',')
            try:
                ch = project.source.getChange(event, refresh=True)
                if ch.project.name != project.name:
                    errors += ('Change %s does not belong to project "%s", '
                               % (args['change'], project.name))
            except Exception:
                errors += 'Invalid change: %s\n' % (args['change'],)

        if errors:
            self.zk_work.complete(work_item.path, errors, success=False)
        else:
            self.sched.enqueue(event)
            self.zk_work.complete(work_item.path)

    def handle_enqueue_ref(self, work_item: ZooKeeperWorkItem):
        (args, event, errors, project) = self._common_enqueue(work_item)

        if not errors:
            event.ref = args['ref']
            event.oldrev = args['oldrev']
            event.newrev = args['newrev']
            try:
                int(event.oldrev, 16)
                if len(event.oldrev) != 40:
                    errors += 'Old rev must be 40 character sha1: ' \
                              '%s\n' % event.oldrev
            except Exception:
                errors += 'Old rev must be base16 hash: ' \
                          '%s\n' % event.oldrev
            try:
                int(event.newrev, 16)
                if len(event.newrev) != 40:
                    errors += 'New rev must be 40 character sha1: ' \
                              '%s\n' % event.newrev
            except Exception:
                errors += 'New rev must be base16 hash: ' \
                          '%s\n' % event.newrev

        if errors:
            self.zk_work.complete(work_item.path, errors, success=False)
        else:
            self.sched.enqueue(event)
            self.zk_work.complete(work_item.path)

    def handle_promote(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant_name = args['tenant']
        pipeline_name = args['pipeline']
        change_ids = args['change_ids']
        self.sched.promote(tenant_name, pipeline_name, change_ids)
        self.zk_work.complete(work_item.path)


class RPCListener(RPCListenerBase):
    log = logging.getLogger("zuul.RPCListener")
    thread_name = 'zuul-rpc-gearman-worker'
    functions = [
        'autohold',
        'autohold_delete',
        'autohold_info',
        'autohold_list',
        'allowed_labels_get',
        'get_admin_tenants',
        'get_running_jobs',
        'get_job_log_stream_address',
        'tenant_list',
        'tenant_sql_connection',
        'status_get',
        'job_get',
        'job_list',
        'project_get',
        'project_list',
        'project_freeze_jobs',
        'pipeline_list',
        'key_get',
        'config_errors_list',
        'connection_list',
        'authorize_user',
    ]

    def start(self):
        super().start()

    def stop(self):
        super().stop()

    def join(self):
        super().join()

    def handle_autohold_info(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        request_id = args['request_id']
        try:
            data = self.sched.autohold_info(request_id)
        except Exception as e:
            self.zk_work.complete(work_item.path, str(e), success=False)
            return
        self.zk_work.complete(work_item.path, data)

    def handle_autohold_delete(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        request_id = args['request_id']
        try:
            self.sched.autohold_delete(request_id)
        except Exception as e:
            self.zk_work.complete(work_item.path, str(e), success=False)
            return
        self.zk_work.complete(work_item.path)

    def handle_autohold_list(self, work_item: ZooKeeperWorkItem):
        data = self.sched.autohold_list()
        self.zk_work.complete(work_item.path, data)

    def handle_autohold(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        params = {}

        tenant = self.sched.abide.tenants.get(args['tenant'])
        if tenant:
            params['tenant_name'] = args['tenant']
        else:
            error = "Invalid tenant: %s" % args['tenant']
            self.zk_work.complete(work_item.path, error, success=False)
            return

        (trusted, project) = tenant.getProject(args['project'])
        if project:
            params['project_name'] = project.canonical_name
        else:
            error = "Invalid project: %s" % args['project']
            self.zk_work.complete(work_item.path, error, success=False)
            return

        if args['change'] and args['ref']:
            self.zk_work.complete(
                work_item.path,
                "Change and ref can't be both used for the same request",
                success=False)

        if args['change']:
            # Convert change into ref based on zuul connection
            ref_filter = project.source.getRefForChange(args['change'])
        elif args['ref']:
            ref_filter = "%s" % args['ref']
        else:
            ref_filter = ".*"

        params['job_name'] = args['job']
        params['ref_filter'] = ref_filter
        params['reason'] = args['reason']

        if args['count'] < 0:
            error = "Invalid count: %d" % args['count']
            self.zk_work.complete(work_item.path, error, success=False)
            return

        params['count'] = args['count']
        params['node_hold_expiration'] = args['node_hold_expiration']

        self.sched.autohold(**params)
        self.zk_work.complete(work_item.path)

    def handle_get_running_jobs(self, work_item: ZooKeeperWorkItem):
        # args = json.loads(job.arguments)
        # TODO: use args to filter by pipeline etc
        running_items = []
        for tenant in self.sched.abide.tenants.values():
            if tenant.layout:
                for pipeline_name, pipeline in tenant.layout.pipelines.items():
                    for queue in pipeline.queues:
                        for item in queue.queue:
                            running_items.append(item.formatJSON())

        self.zk_work.complete(work_item.path, running_items)

    def handle_get_job_log_stream_address(self, work_item: ZooKeeperWorkItem):
        # TODO: map log files to ports. Currently there is only one
        #       log stream for a given job. But many jobs produce many
        #       log files, so this is forwards compatible with a future
        #       where there are more logs to potentially request than
        #       "console.log"
        def find_build(uuid: str) -> Optional[Build]:
            for tenant in self.sched.abide.tenants.values():
                if tenant.layout:
                    for pipeline_name, pipeline in tenant.layout.pipelines\
                            .items():
                        for queue in pipeline.queues:
                            for item in queue.queue:
                                for bld in item.current_build_set.getBuilds():
                                    if bld.uuid == uuid:
                                        return bld
            return None

        args = work_item.content['params']
        uuid = args['uuid']
        # TODO: logfile = args['logfile']
        job_log_stream_address = {}
        build = find_build(uuid)
        if build:
            job_log_stream_address['server'] = build.worker.hostname
            job_log_stream_address['port'] = build.worker.log_port
        self.zk_work.complete(work_item.path, job_log_stream_address)

    def _is_authorized(self, tenant, claims):
        authorized = False
        if tenant:
            rules = tenant.authorization_rules
            for rule in rules:
                if rule not in self.sched.abide.admin_rules.keys():
                    self.log.error('Undefined rule "%s"' % rule)
                    continue
                debug_msg = ('Applying rule "%s" from tenant '
                             '"%s" to claims %s')
                self.log.debug(
                    debug_msg % (rule, tenant, json.dumps(claims)))
                authorized = self.sched.abide.admin_rules[rule](claims,
                                                                tenant)
                if authorized:
                    if '__zuul_uid_claim' in claims:
                        uid = claims['__zuul_uid_claim']
                    else:
                        uid = json.dumps(claims)
                    msg = '%s authorized on tenant "%s" by rule "%s"'
                    self.log.info(
                        msg % (uid, tenant, rule))
                    break
        return authorized

    def handle_authorize_user(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant_name = args['tenant']
        claims = args['claims']
        tenant = self.sched.abide.tenants.get(tenant_name)
        authorized = self._is_authorized(tenant, claims)
        self.zk_work.complete(work_item.path, authorized)

    def handle_get_admin_tenants(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        claims = args['claims']
        admin_tenants = []
        for tenant_name, tenant in self.sched.abide.tenants.items():
            if self._is_authorized(tenant, claims):
                admin_tenants.append(tenant_name)
        self.zk_work.complete(work_item.path, admin_tenants)

    def handle_tenant_list(self, work_item: ZooKeeperWorkItem):
        output = []
        for tenant_name, tenant in self.sched.abide.tenants.items():
            queue_size = 0
            if tenant.layout:
                for pipeline_name, pipeline in tenant.layout.pipelines.items():
                    for queue in pipeline.queues:
                        for item in queue.queue:
                            if item.live:
                                queue_size += 1

            output.append({'name': tenant_name,
                           'projects': len(tenant.untrusted_projects),
                           'queue': queue_size})
        self.zk_work.complete(work_item.path, output)

    def handle_tenant_sql_connection(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        sql_driver = self.sched.connections.drivers['sql']
        conn = sql_driver.tenant_connections.get(args['tenant'])
        if conn:
            name = conn.connection_name
        else:
            name = ''
        self.zk_work.complete(work_item.path, name)

    def handle_status_get(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        output = self.sched.formatStatus(args.get("tenant"))
        self.zk_work.complete(work_item.path, output)

    def handle_job_get(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        jobs = tenant.layout.jobs.get(args.get("job"), [])\
            if tenant.layout else []  # TODO JK
        output = []
        for job in jobs:
            output.append(job.toDict(tenant))
        self.zk_work.complete(work_item.path,
                              json.dumps(output, cls=ZuulJSONEncoder))

    def handle_job_list(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        output = []
        if not tenant or not tenant.layout:
            self.zk_work.complete(work_item.path, None)
            return
        for job_name in sorted(tenant.layout.jobs):
            desc = None
            tags = set()
            variants = []
            if not tenant.layout:
                continue  # TODO JK
            for variant in tenant.layout.jobs[job_name]:
                if not desc and variant.description:
                    desc = variant.description.split('\n')[0]
                if variant.tags:
                    tags.update(list(variant.tags))
                job_variant = {}
                if not variant.isBase():
                    if variant.parent:
                        job_variant['parent'] = str(variant.parent)
                    else:
                        job_variant['parent'] = tenant.default_base_job\
                            if tenant else None  # TODO JK
                branches = variant.getBranches()
                if branches:
                    job_variant['branches'] = branches
                if job_variant:
                    variants.append(job_variant)

            job_output = {
                "name": job_name,
            }
            if desc:
                job_output["description"] = desc
            if variants:
                job_output["variants"] = variants
            if tags:
                job_output["tags"] = list(tags)
            output.append(job_output)
        self.zk_work.complete(work_item.path, output)

    def handle_project_get(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args["tenant"])
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        trusted, project = tenant.getProject(args["project"])
        if not project:
            self.zk_work.complete(work_item.path, {})
            return
        result = project.toDict()
        result['configs'] = []
        configs = tenant.layout.getAllProjectConfigs(project.canonical_name)\
            if tenant.layout else []  # TODO JK
        for config_obj in configs:
            config = config_obj.toDict()
            config['pipelines'] = []
            for pipeline_name, pipeline_config in sorted(
                    config_obj.pipelines.items()):
                pipeline = pipeline_config.toDict()
                pipeline['name'] = pipeline_name
                pipeline['jobs'] = []
                for jobs in pipeline_config.job_list.jobs.values():
                    job_list = []
                    for job in jobs:
                        job_list.append(job.toDict(tenant))
                    pipeline['jobs'].append(job_list)
                config['pipelines'].append(pipeline)
            result['configs'].append(config)

        self.zk_work.complete(work_item.path,
                              json.dumps(result, cls=ZuulJSONEncoder))

    def handle_project_list(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        output = []
        for project in tenant.config_projects:
            pobj = project.toDict()
            pobj['type'] = "config"
            output.append(pobj)
        for project in tenant.untrusted_projects:
            pobj = project.toDict()
            pobj['type'] = "untrusted"
            output.append(pobj)
        self.zk_work.complete(
            work_item.path, sorted(output, key=lambda p: p["name"]))

    def handle_project_freeze_jobs(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        project = None
        pipeline = None
        if tenant:
            (trusted, project) = tenant.getProject(args.get("project"))
            pipeline = tenant.layout.pipelines.get(args.get("pipeline"))\
                if tenant.layout else None  # TODO JK
        if not project or not pipeline:
            self.zk_work.complete(work_item.path, None)
            return

        change = model.Branch(project)
        change.branch = args.get("branch", "master")
        queue = model.ChangeQueue(pipeline)
        item = model.QueueItem(queue, change, None)
        item.layout = tenant.layout if tenant else None
        item.freezeJobGraph(skip_file_matcher=True)

        output = []

        if item.job_graph:
            for job in item.job_graph.getJobs():
                if not tenant:
                    continue
                job.setBase(tenant.layout)
                output.append({
                    'name': job.name,
                    'dependencies':
                        list(map(lambda x: x.toDict(), job.dependencies)),
                })

        self.zk_work.complete(work_item.path, output)

    def handle_allowed_labels_get(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        ret = {}
        ret['allowed_labels'] = tenant.allowed_labels or []
        ret['disallowed_labels'] = tenant.disallowed_labels or []
        self.zk_work.complete(work_item.path, ret)

    def handle_pipeline_list(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        output = []
        if tenant.layout:
            for pipeline, pipeline_config in tenant.layout.pipelines.items():
                triggers = []
                for trigger in pipeline_config.triggers:
                    if isinstance(trigger.connection, BaseConnection):
                        name = trigger.connection.connection_name
                    else:
                        # Trigger not based on a connection doesn't use this
                        # attr
                        name = trigger.name
                    triggers.append({
                        "name": name,
                        "driver": trigger.driver.name,
                    })
                output.append({"name": pipeline, "triggers": triggers})
        self.zk_work.complete(work_item.path, output)

    def handle_key_get(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        project = None
        if tenant:
            (trusted, project) = tenant.getProject(args.get("project"))
        if not project:
            self.zk_work.complete(work_item.path, "")
            return
        keytype = args.get('key', 'secrets')
        if keytype == 'secrets':
            self.zk_work.complete(work_item.path,
                                  encryption.serialize_rsa_public_key(
                                      project.public_secrets_key))
        elif keytype == 'ssh':
            self.zk_work.complete(work_item.path, project.public_ssh_key)
        else:
            self.zk_work.complete(work_item.path, "")
            return

    def handle_config_errors_list(self, work_item: ZooKeeperWorkItem):
        args = work_item.content['params']
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        output = []
        if not tenant:
            self.zk_work.complete(work_item.path, None)
            return
        if tenant.layout:
            for err in tenant.layout.loading_errors.errors:
                output.append({
                    'source_context': err.key.context.toDict(),
                    'error': err.error})
        self.zk_work.complete(work_item.path, output)

    def handle_connection_list(self, work_item: ZooKeeperWorkItem):
        output = []
        for source in self.sched.connections.getSources():
            output.append(source.connection.toDict())
        self.zk_work.complete(work_item.path, output)
