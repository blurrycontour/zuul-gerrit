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
import time
from abc import ABCMeta
from typing import List

from zuul.connection import BaseConnection
from zuul.lib import encryption
from zuul.lib.gearworker import ZuulGearWorker
from zuul.lib.jsonutil import ZuulJSONEncoder


class RPCListenerBase(metaclass=ABCMeta):
    log = logging.getLogger("zuul.RPCListenerBase")
    thread_name = 'zuul-rpc-gearman-worker'
    functions = []  # type: List[str]

    def __init__(self, config, sched):
        self.config = config
        self.sched = sched

        self.jobs = {}

        for func in self.functions:
            f = getattr(self, 'handle_%s' % func)
            self.jobs['zuul:%s' % func] = f
        self.gearworker = ZuulGearWorker(
            'Zuul RPC Listener',
            self.log.name,
            self.thread_name,
            self.config,
            self.jobs)

    def start(self):
        self.gearworker.start()

    def stop(self):
        self.log.debug("Stopping")
        self.gearworker.stop()
        self.log.debug("Stopped")

    def join(self):
        self.gearworker.join()


class RPCListenerSlow(RPCListenerBase):
    log = logging.getLogger("zuul.RPCListenerSlow")
    thread_name = 'zuul-rpc-slow-gearman-worker'
    functions = [
        'dequeue',
        'enqueue',
        'enqueue_ref',
        'promote',
    ]

    def handle_dequeue(self, job):
        args = json.loads(job.arguments)
        tenant_name = args['tenant']
        pipeline_name = args['pipeline']
        project_name = args['project']
        change = args['change']
        ref = args['ref']
        try:
            self.sched.dequeue(
                tenant_name, pipeline_name, project_name, change, ref)
        except Exception as e:
            job.sendWorkException(str(e).encode('utf8'))
            return
        job.sendWorkComplete()

    def _common_enqueue(self, job, args):
        tenant_name = args['tenant']
        pipeline_name = args['pipeline']
        project_name = args['project']
        change = args.get('change')
        ref = args.get('ref')
        oldrev = args.get('oldrev')
        newrev = args.get('newrev')
        try:
            self.sched.enqueue(tenant_name, pipeline_name, project_name,
                               change, ref, oldrev, newrev)
        except Exception as e:
            job.sendWorkException(str(e).encode('utf8'))
            return

        job.sendWorkComplete()

    def handle_enqueue(self, job):
        args = json.loads(job.arguments)
        self._common_enqueue(job, args)

    def handle_enqueue_ref(self, job):
        args = json.loads(job.arguments)
        oldrev = args['oldrev']
        newrev = args['newrev']
        errors = ''
        try:
            int(oldrev, 16)
            if len(oldrev) != 40:
                errors += f'Old rev must be 40 character sha1: {oldrev}\n'
        except Exception:
            errors += f'Old rev must be base16 hash: {oldrev}\n'
        try:
            int(newrev, 16)
            if len(newrev) != 40:
                errors += f'New rev must be 40 character sha1: {newrev}\n'
        except Exception:
            errors += f'New rev must be base16 hash: {newrev}\n'

        if errors:
            job.sendWorkException(errors.encode('utf8'))
        else:
            self._common_enqueue(job, args)

    def handle_promote(self, job):
        args = json.loads(job.arguments)
        tenant_name = args['tenant']
        pipeline_name = args['pipeline']
        change_ids = args['change_ids']
        self.sched.promote(tenant_name, pipeline_name, change_ids)
        job.sendWorkComplete()


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
        'tenant_list',
        'status_get',
        'pipeline_list',
        'key_get',
        'config_errors_list',
        'connection_list',
        'authorize_user',
    ]

    def start(self):
        self.gearworker.start()

    def stop(self):
        self.log.debug("Stopping")
        self.gearworker.stop()
        self.log.debug("Stopped")

    def join(self):
        self.gearworker.join()

    def handle_autohold_info(self, job):
        args = json.loads(job.arguments)
        request_id = args['request_id']
        try:
            data = self.sched.autohold_info(request_id)
        except Exception as e:
            job.sendWorkException(str(e).encode('utf8'))
            return
        job.sendWorkComplete(json.dumps(data))

    def handle_autohold_delete(self, job):
        args = json.loads(job.arguments)
        request_id = args['request_id']
        try:
            self.sched.autohold_delete(request_id)
        except Exception as e:
            job.sendWorkException(str(e).encode('utf8'))
            return
        job.sendWorkComplete()

    def handle_autohold_list(self, job):
        data = self.sched.autohold_list()
        job.sendWorkComplete(json.dumps(data))

    def handle_autohold(self, job):
        args = json.loads(job.arguments)
        params = {}

        tenant = self.sched.abide.tenants.get(args['tenant'])
        if tenant:
            params['tenant_name'] = args['tenant']
        else:
            error = "Invalid tenant: %s" % args['tenant']
            job.sendWorkException(error.encode('utf8'))
            return

        (trusted, project) = tenant.getProject(args['project'])
        if project:
            params['project_name'] = project.canonical_name
        else:
            error = "Invalid project: %s" % args['project']
            job.sendWorkException(error.encode('utf8'))
            return

        if args['change'] and args['ref']:
            job.sendWorkException("Change and ref can't be both used "
                                  "for the same request")

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
            job.sendWorkException(error.encode('utf8'))
            return

        params['count'] = args['count']
        params['node_hold_expiration'] = args['node_hold_expiration']

        self.sched.autohold(**params)
        job.sendWorkComplete()

    def handle_get_running_jobs(self, job):
        # args = json.loads(job.arguments)
        # TODO: use args to filter by pipeline etc
        running_items = []
        for tenant in self.sched.abide.tenants.values():
            for pipeline_name, pipeline in tenant.layout.pipelines.items():
                for queue in pipeline.queues:
                    for item in queue.queue:
                        running_items.append(item.formatJSON())

        job.sendWorkComplete(json.dumps(running_items))

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

    def handle_authorize_user(self, job):
        args = json.loads(job.arguments)
        tenant_name = args['tenant']
        claims = args['claims']
        tenant = self.sched.abide.tenants.get(tenant_name)
        authorized = self._is_authorized(tenant, claims)
        job.sendWorkComplete(json.dumps(authorized))

    def handle_get_admin_tenants(self, job):
        args = json.loads(job.arguments)
        claims = args['claims']
        admin_tenants = []
        for tenant_name, tenant in self.sched.abide.tenants.items():
            if self._is_authorized(tenant, claims):
                admin_tenants.append(tenant_name)
        job.sendWorkComplete(json.dumps(admin_tenants))

    def handle_tenant_list(self, job):
        output = []
        for tenant_name, tenant in sorted(self.sched.abide.tenants.items()):
            queue_size = 0
            for pipeline_name, pipeline in tenant.layout.pipelines.items():
                for queue in pipeline.queues:
                    for item in queue.queue:
                        if item.live:
                            queue_size += 1

            output.append({'name': tenant_name,
                           'projects': len(tenant.untrusted_projects),
                           'queue': queue_size})
        job.sendWorkComplete(json.dumps(output))

    def handle_status_get(self, job):
        args = json.loads(job.arguments)
        start = time.monotonic()
        output = self.sched.formatStatusJSON(args.get("tenant"))
        end = time.monotonic()
        self.log.debug('Formatting tenant %s status took %.3f seconds for '
                       '%d bytes', args.get("tenant"), end - start,
                       len(output))
        job.sendWorkComplete(output)

    def handle_allowed_labels_get(self, job):
        args = json.loads(job.arguments)
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            job.sendWorkComplete(json.dumps(None))
            return
        ret = {}
        ret['allowed_labels'] = tenant.allowed_labels or []
        ret['disallowed_labels'] = tenant.disallowed_labels or []
        job.sendWorkComplete(json.dumps(ret))

    def handle_pipeline_list(self, job):
        args = json.loads(job.arguments)
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        if not tenant:
            job.sendWorkComplete(json.dumps(None))
            return
        output = []
        for pipeline, pipeline_config in tenant.layout.pipelines.items():
            triggers = []
            for trigger in pipeline_config.triggers:
                if isinstance(trigger.connection, BaseConnection):
                    name = trigger.connection.connection_name
                else:
                    # Trigger not based on a connection doesn't use this attr
                    name = trigger.name
                triggers.append({
                    "name": name,
                    "driver": trigger.driver.name,
                })
            output.append({"name": pipeline, "triggers": triggers})
        job.sendWorkComplete(json.dumps(output))

    def handle_key_get(self, job):
        args = json.loads(job.arguments)
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        project = None
        if tenant:
            (trusted, project) = tenant.getProject(args.get("project"))
        if not project:
            job.sendWorkComplete("")
            return
        keytype = args.get('key', 'secrets')
        if keytype == 'secrets':
            job.sendWorkComplete(
                encryption.serialize_rsa_public_key(
                    project.public_secrets_key))
        elif keytype == 'ssh':
            job.sendWorkComplete(project.public_ssh_key)
        else:
            job.sendWorkComplete("")
            return

    def handle_config_errors_list(self, job):
        args = json.loads(job.arguments)
        tenant = self.sched.abide.tenants.get(args.get("tenant"))
        output = []
        if not tenant:
            job.sendWorkComplete(json.dumps(None))
            return
        for err in tenant.layout.loading_errors.errors:
            output.append({
                'source_context': err.key.context.toDict(),
                'error': err.error})
        job.sendWorkComplete(json.dumps(output))

    def handle_connection_list(self, job):
        output = []
        for source in self.sched.connections.getSources():
            output.append(source.connection.toDict())
        job.sendWorkComplete(json.dumps(output))
