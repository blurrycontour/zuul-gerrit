# Copyright 2012-2015 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
# Copyright 2013 Antoine "hashar" Musso
# Copyright 2013 Wikimedia Foundation Inc.
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
import re
import socket
import sys
import threading
import time
import traceback
import urllib

from kazoo.exceptions import NotEmptyError

from zuul import configloader
from zuul import model
from zuul import exceptions
from zuul import version as zuul_version
from zuul import rpclistener
from zuul.lib import commandsocket
from zuul.lib.ansible import AnsibleManager
from zuul.lib.config import get_default
from zuul.lib.gear_utils import getGearmanFunctions
from zuul.lib.keystorage import FileKeyStorage, ZooKeeperKeyStorage
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.queue import NamedQueue
from zuul.lib.statsd import get_statsd, normalize_statsd_name
import zuul.lib.queue
import zuul.lib.repl
from zuul import nodepool
from zuul.executor.client import ExecutorClient
from zuul.merger.client import MergeClient
from zuul.model import (
    Abide,
    Build,
    BuildCompletedEvent,
    BuildPausedEvent,
    BuildStartedEvent,
    BuildStatusEvent,
    ChangeManagementEvent,
    DequeueEvent,
    EnqueueEvent,
    FilesChangesCompletedEvent,
    HoldRequest,
    MergeCompletedEvent,
    NodesProvisionedEvent,
    PromoteEvent,
    ReconfigureEvent,
    SmartReconfigureEvent,
    Tenant,
    TenantReconfigureEvent,
    UnparsedAbideConfig,
)
from zuul.zk import ZooKeeperClient
from zuul.zk.components import (
    BaseComponent, ComponentRegistry, SchedulerComponent
)
from zuul.zk.config_cache import UnparsedConfigCache
from zuul.zk.event_queues import (
    GlobalEventWatcher,
    GlobalManagementEventQueue,
    GlobalTriggerEventQueue,
    PipelineEventWatcher,
    PipelineManagementEventQueue,
    PipelineResultEventQueue,
    PipelineTriggerEventQueue,
    TENANT_ROOT,
)
from zuul.zk.nodepool import ZooKeeperNodepool

COMMANDS = ['full-reconfigure', 'smart-reconfigure', 'stop', 'repl', 'norepl']


class Scheduler(threading.Thread):
    """The engine of Zuul.

    The Scheduler is responsible for receiving events and dispatching
    them to appropriate components (including pipeline managers,
    mergers and executors).

    It runs a single threaded main loop which processes events
    received one at a time and takes action as appropriate.  Other
    parts of Zuul may run in their own thread, but synchronization is
    performed within the scheduler to reduce or eliminate the need for
    locking in most circumstances.

    The main daemon will have one instance of the Scheduler class
    running which will persist for the life of the process.  The
    Scheduler instance is supplied to other Zuul components so that
    they can submit events or otherwise communicate with other
    components.

    """

    log = logging.getLogger("zuul.Scheduler")
    _stats_interval = 30
    _cleanup_interval = 60 * 60
    _merger_client_class = MergeClient

    # Number of seconds past node expiration a hold request will remain
    EXPIRED_HOLD_REQUEST_TTL = 24 * 60 * 60

    def __init__(self, config, connections, app, testonly=False):
        threading.Thread.__init__(self)
        self.daemon = True
        self.hostname = socket.getfqdn()
        self.wake_event = threading.Event()
        self.layout_lock = threading.Lock()
        self.run_handler_lock = threading.Lock()
        self.command_map = {
            'stop': self.stop,
            'full-reconfigure': self.fullReconfigureCommandHandler,
            'smart-reconfigure': self.smartReconfigureCommandHandler,
            'repl': self.start_repl,
            'norepl': self.stop_repl,
        }
        self._stopped = False

        self._zuul_app = app
        self.connections = connections
        self.statsd = get_statsd(config)
        self.rpc = rpclistener.RPCListener(config, self)
        self.rpc_slow = rpclistener.RPCListenerSlow(config, self)
        self.repl = None
        self.stats_thread = threading.Thread(target=self.runStats)
        self.stats_thread.daemon = True
        self.stats_stop = threading.Event()
        self.cleanup_thread = threading.Thread(target=self.runCleanup)
        self.cleanup_thread.daemon = True
        self.cleanup_stop = threading.Event()
        # TODO(jeblair): fix this
        # Despite triggers being part of the pipeline, there is one trigger set
        # per scheduler. The pipeline handles the trigger filters but since
        # the events are handled by the scheduler itself it needs to handle
        # the loading of the triggers.
        # self.triggers['connection_name'] = triggerObject
        self.triggers = dict()
        self.config = config

        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()
        self.zk_nodepool = ZooKeeperNodepool(self.zk_client)
        self.component_info = SchedulerComponent(self.zk_client, self.hostname)
        self.component_info.register()
        self.component_registry = ComponentRegistry(self.zk_client)
        self.unparsed_config_cache = UnparsedConfigCache(self.zk_client)

        self.result_event_queue = NamedQueue("ResultEventQueue")
        self.global_watcher = GlobalEventWatcher(
            self.zk_client, self.wake_event.set
        )
        self.pipeline_watcher = PipelineEventWatcher(
            self.zk_client, self.wake_event.set
        )
        self.management_events = GlobalManagementEventQueue(self.zk_client)
        self.pipeline_management_events = (
            PipelineManagementEventQueue.createRegistry(
                self.zk_client
            )
        )
        self.trigger_events = GlobalTriggerEventQueue(
            self.zk_client, self.connections
        )
        self.pipeline_trigger_events = (
            PipelineTriggerEventQueue.createRegistry(
                self.zk_client, self.connections
            )
        )
        self.pipeline_result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )
        self.abide = Abide()
        self.unparsed_abide = UnparsedAbideConfig()

        if not testonly:
            time_dir = self._get_time_database_dir()
            self.time_database = model.TimeDataBase(time_dir)

        command_socket = get_default(
            self.config, 'scheduler', 'command_socket',
            '/var/lib/zuul/scheduler.socket')
        self.command_socket = commandsocket.CommandSocket(command_socket)

        if zuul_version.is_release is False:
            self.zuul_version = "%s %s" % (zuul_version.release_string,
                                           zuul_version.git_version)
        else:
            self.zuul_version = zuul_version.release_string
        self.last_reconfigured = None
        self.tenant_last_reconfigured = {}
        self.use_relative_priority = False
        if self.config.has_option('scheduler', 'relative_priority'):
            if self.config.getboolean('scheduler', 'relative_priority'):
                self.use_relative_priority = True
        web_root = get_default(self.config, 'web', 'root', None)
        if web_root:
            web_root = urllib.parse.urljoin(web_root, 't/{tenant.name}/')
        self.web_root = web_root

        default_ansible_version = get_default(
            self.config, 'scheduler', 'default_ansible_version', None)
        self.ansible_manager = AnsibleManager(
            default_version=default_ansible_version)

        if not testonly:
            self.executor = ExecutorClient(self.config, self)
            self.merger = self._merger_client_class(self.config, self)
            self.nodepool = nodepool.Nodepool(
                self.zk_client, self.hostname, self.statsd, self)

    def start(self):
        super(Scheduler, self).start()
        self.keystore = ZooKeeperKeyStorage(
            self.zk_client,
            password=self._get_key_store_password(),
            backup=FileKeyStorage(self._get_key_dir()))

        self._command_running = True
        self.log.debug("Starting command processor")
        self.command_socket.start()
        self.command_thread = threading.Thread(target=self.runCommand,
                                               name='command')
        self.command_thread.daemon = True
        self.command_thread.start()

        self.rpc.start()
        self.rpc_slow.start()
        self.stats_thread.start()
        self.cleanup_thread.start()
        self.component_info.state = self.component_info.RUNNING

    def stop(self):
        self._stopped = True
        self.component_info.state = self.component_info.STOPPED
        self.stats_stop.set()
        self.cleanup_stop.set()
        self.stopConnections()
        self.wake_event.set()
        self.stats_thread.join()
        self.cleanup_thread.join()
        self.rpc.stop()
        self.rpc.join()
        self.rpc_slow.stop()
        self.rpc_slow.join()
        self.stop_repl()
        self._command_running = False
        self.command_socket.stop()
        self.command_thread.join()
        self.zk_client.disconnect()

    def runCommand(self):
        while self._command_running:
            try:
                command = self.command_socket.get().decode('utf8')
                if command != '_stop':
                    self.command_map[command]()
            except Exception:
                self.log.exception("Exception while processing command")

    def stopConnections(self):
        self.connections.stop()

    def runStats(self):
        while not self.stats_stop.wait(self._stats_interval):
            try:
                self._runStats()
            except Exception:
                self.log.exception("Error in periodic stats:")

    def _runStats(self):
        if not self.statsd:
            return

        # Calculate the executor and merger stats
        executors_online = 0
        executors_accepting = 0
        executors_unzoned_online = 0
        executors_unzoned_accepting = 0
        # zone -> accepting|online
        zoned_executor_stats = {}

        mergers_online = 0

        for executor_component in self.component_registry.all("executor"):
            if executor_component.allow_unzoned or not executor_component.zone:
                if executor_component.state == BaseComponent.RUNNING:
                    executors_unzoned_online += 1
                if executor_component.accepting_work:
                    executors_unzoned_accepting += 1
            else:
                zone_stats = zoned_executor_stats.setdefault(
                    executor_component.zone, {"online": 0, "accepting": 0}
                )
                if executor_component.state == BaseComponent.RUNNING:
                    zone_stats["online"] += 1
                if executor_component.accepting_work:
                    zone_stats["accepting"] += 1
            # An executor with merger capabilities does also count as merger
            if executor_component.process_merge_jobs:
                mergers_online += 1

            # TODO(corvus): Remove for 5.0:
            executors_online += 1
            executors_accepting += 1

        for merger_component in self.component_registry.all("merger"):
            if merger_component.state == BaseComponent.RUNNING:
                mergers_online += 1

        # Publish the executor stats
        self.statsd.gauge(
            'zuul.executors.unzoned.accepting', executors_unzoned_accepting
        )
        self.statsd.gauge(
            'zuul.executors.unzoned.online', executors_unzoned_online
        )
        for zone, stats in zoned_executor_stats.items():
            self.statsd.gauge(
                f'zuul.executors.zone.{normalize_statsd_name(zone)}.accepting',
                stats["accepting"],
            )
            self.statsd.gauge(
                f'zuul.executors.zone.{normalize_statsd_name(zone)}.online',
                stats["online"],
            )

        # TODO(corvus): Remove for 5.0:
        self.statsd.gauge('zuul.executors.accepting', executors_accepting)
        self.statsd.gauge('zuul.executors.online', executors_online)

        # Publish the merger stats
        self.statsd.gauge('zuul.mergers.online', mergers_online)

        functions = getGearmanFunctions(self.rpc.gearworker.gearman)
        functions.update(getGearmanFunctions(self.rpc_slow.gearworker.gearman))
        merge_queue = 0
        merge_running = 0
        for (name, (queued, running, registered)) in functions.items():
            if name.startswith('executor:execute'):
                execute_queue = queued - running
                tokens = name.split(':', 2)
                if len(tokens) == 2:
                    # unzoned case
                    self.statsd.gauge('zuul.executors.unzoned.jobs_running',
                                      running)
                    self.statsd.gauge('zuul.executors.unzoned.jobs_queued',
                                      execute_queue)
                    # TODO(corvus): Remove for 5.0:
                    self.statsd.gauge('zuul.executors.jobs_running',
                                      running)
                    self.statsd.gauge('zuul.executors.jobs_queued',
                                      execute_queue)
                else:
                    # zoned case
                    zone = tokens[2]
                    self.statsd.gauge('zuul.executors.zone.%s.jobs_running' %
                                      normalize_statsd_name(zone),
                                      running)
                    self.statsd.gauge('zuul.executors.zone.%s.jobs_queued' %
                                      normalize_statsd_name(zone),
                                      execute_queue)

            if name == 'merger:merge':
                mergers_online = registered
            if name.startswith('merger:'):
                merge_queue += queued - running
                merge_running += running
        self.statsd.gauge('zuul.mergers.jobs_running', merge_running)
        self.statsd.gauge('zuul.mergers.jobs_queued', merge_queue)
        self.statsd.gauge('zuul.scheduler.eventqueues.trigger',
                          len(self.trigger_events))
        self.statsd.gauge('zuul.scheduler.eventqueues.result',
                          self.result_event_queue.qsize())
        self.statsd.gauge('zuul.scheduler.eventqueues.management',
                          len(self.management_events))
        base = 'zuul.scheduler.eventqueues.connection'
        for connection in self.connections.connections.values():
            queue = connection.getEventQueue()
            if queue is not None:
                self.statsd.gauge(f'{base}.{connection.connection_name}',
                                  len(queue))

        for tenant in self.abide.tenants.values():
            trigger_event_queues = self.pipeline_trigger_events[tenant.name]
            result_event_queues = self.pipeline_result_events[tenant.name]
            management_event_queues = (
                self.pipeline_management_events[tenant.name]
            )
            for pipeline in tenant.layout.pipelines.values():
                base = f"zuul.tenant.{tenant.name}.pipeline.{pipeline.name}"
                self.statsd.gauge(f"{base}.trigger_events",
                                  len(trigger_event_queues[pipeline.name]))
                self.statsd.gauge(f"{base}.result_events",
                                  len(result_event_queues[pipeline.name]))
                self.statsd.gauge(f"{base}.management_events",
                                  len(management_event_queues[pipeline.name]))

    def runCleanup(self):
        # Run the first cleanup immediately after the first
        # reconfiguration.
        interval = 0
        while not self.cleanup_stop.wait(interval):
            try:
                if not self.last_reconfigured:
                    time.sleep(1)
                    continue
                self._runCleanup()
            except Exception:
                self.log.exception("Error in periodic cleanup:")
            interval = self._cleanup_interval

    def _runCleanup(self):
        # Get the layout lock to make sure the abide doesn't change
        # under us.
        with self.layout_lock:
            self.log.debug("Starting semaphore cleanup")
            for tenant in self.abide.tenants.values():
                try:
                    tenant.semaphore_handler.cleanupLeaks()
                except Exception:
                    self.log.exception("Error in semaphore cleanup:")

            cached_projects = set(
                self.unparsed_config_cache.listCachedProjects())
            active_projects = set(
                self.abide.unparsed_project_branch_cache.keys())
            unused_projects = cached_projects - active_projects
            for project_cname in unused_projects:
                self.unparsed_config_cache.clearCache(project_cname)

    def addTriggerEvent(self, driver_name, event):
        event.arrived_at_scheduler_timestamp = time.time()
        self.trigger_events.put(driver_name, event)
        self.wake_event.set()

    def addManagementEvent(self, event):
        self.management_events.put(event, needs_result=False)

    def addResultEvent(self, event):
        self.result_event_queue.put(event)
        self.wake_event.set()

    def _reportBuildStats(self, build):
        # Note, as soon as the result is set, other threads may act
        # upon this, even though the event hasn't been fully
        # processed. This could result in race conditions when e.g. skipping
        # child jobs via zuul_return. Therefore we must delay setting the
        # result to the main event loop.
        try:
            if self.statsd and build.pipeline:
                tenant = build.pipeline.tenant
                jobname = build.job.name.replace('.', '_').replace('/', '_')
                hostname = (build.build_set.item.change.project.
                            canonical_hostname.replace('.', '_'))
                projectname = (build.build_set.item.change.project.name.
                               replace('.', '_').replace('/', '_'))
                branchname = (getattr(build.build_set.item.change,
                                      'branch', '').
                              replace('.', '_').replace('/', '_'))
                basekey = 'zuul.tenant.%s' % tenant.name
                pipekey = '%s.pipeline.%s' % (basekey, build.pipeline.name)
                # zuul.tenant.<tenant>.pipeline.<pipeline>.all_jobs
                key = '%s.all_jobs' % pipekey
                self.statsd.incr(key)
                jobkey = '%s.project.%s.%s.%s.job.%s' % (
                    pipekey, hostname, projectname, branchname, jobname)
                # zuul.tenant.<tenant>.pipeline.<pipeline>.project.
                #   <host>.<project>.<branch>.job.<job>.<result>
                key = '%s.%s' % (
                    jobkey,
                    'RETRY' if build.result is None else build.result
                )
                if build.result in ['SUCCESS', 'FAILURE'] and build.start_time:
                    dt = int((build.end_time - build.start_time) * 1000)
                    self.statsd.timing(key, dt)
                self.statsd.incr(key)
                # zuul.tenant.<tenant>.pipeline.<pipeline>.project.
                #  <host>.<project>.<branch>.job.<job>.wait_time
                if build.start_time:
                    key = '%s.wait_time' % jobkey
                    dt = int((build.start_time - build.execute_time) * 1000)
                    self.statsd.timing(key, dt)
        except Exception:
            self.log.exception("Exception reporting runtime stats")

    def onMergeCompleted(self, build_set, merged, updated,
                         commit, files, repo_state, item_in_branches):
        event = MergeCompletedEvent(build_set, merged, updated,
                                    commit, files, repo_state,
                                    item_in_branches)
        self.result_event_queue.put(event)
        self.wake_event.set()

    def onFilesChangesCompleted(self, build_set, files):
        event = FilesChangesCompletedEvent(build_set, files)
        self.result_event_queue.put(event)
        self.wake_event.set()

    def onNodesProvisioned(self, req):
        event = NodesProvisionedEvent(req)
        self.result_event_queue.put(event)
        self.wake_event.set()

    def reconfigureTenant(self, tenant, project, event):
        self.log.debug("Submitting tenant reconfiguration event for "
                       "%s due to event %s in project %s",
                       tenant.name, event, project)
        branch = event.branch if event is not None else None
        event = TenantReconfigureEvent(
            tenant.name, project.canonical_name, branch
        )
        self.management_events.put(event, needs_result=False)

    def fullReconfigureCommandHandler(self):
        self._zuul_app.fullReconfigure()

    def smartReconfigureCommandHandler(self):
        self._zuul_app.smartReconfigure()

    def start_repl(self):
        if self.repl:
            return
        self.repl = zuul.lib.repl.REPLServer(self)
        self.repl.start()

    def stop_repl(self):
        if not self.repl:
            return
        self.repl.stop()
        self.repl = None

    def prime(self, config, validate_tenants=None):
        self.log.debug("Priming scheduler config")
        event = ReconfigureEvent(validate_tenants=validate_tenants)
        self._doReconfigureEvent(event)
        self.log.debug("Config priming complete")
        self.last_reconfigured = int(time.time())

    def reconfigure(self, config, smart=False):
        self.log.debug("Submitting reconfiguration event")
        if smart:
            event = SmartReconfigureEvent()
        else:
            event = ReconfigureEvent()

        result = self.management_events.put(event)

        self.log.debug("Waiting for reconfiguration")
        result.wait()
        self.log.debug("Reconfiguration complete")
        self.last_reconfigured = int(time.time())
        # TODOv3(jeblair): reconfigure time should be per-tenant

    def autohold(self, tenant_name, project_name, job_name, ref_filter,
                 reason, count, node_hold_expiration):
        key = (tenant_name, project_name, job_name, ref_filter)
        self.log.debug("Autohold requested for %s", key)

        request = HoldRequest()
        request.tenant = tenant_name
        request.project = project_name
        request.job = job_name
        request.ref_filter = ref_filter
        request.reason = reason
        request.max_count = count

        max_hold = get_default(
            self.config, 'scheduler', 'max_hold_expiration', 0)
        default_hold = get_default(
            self.config, 'scheduler', 'default_hold_expiration', max_hold)

        # If the max hold is not infinite, we need to make sure that
        # our default value does not exceed it.
        if max_hold and default_hold != max_hold and (default_hold == 0 or
                                                      default_hold > max_hold):
            default_hold = max_hold

        # Set node_hold_expiration to default if no value is supplied
        if node_hold_expiration is None:
            node_hold_expiration = default_hold

        # Reset node_hold_expiration to max if it exceeds the max
        elif max_hold and (node_hold_expiration == 0 or
                           node_hold_expiration > max_hold):
            node_hold_expiration = max_hold

        request.node_expiration = node_hold_expiration

        # No need to lock it since we are creating a new one.
        self.zk_nodepool.storeHoldRequest(request)

    def autohold_list(self):
        '''
        Return current hold requests as a list of dicts.
        '''
        data = []
        for request_id in self.zk_nodepool.getHoldRequests():
            request = self.zk_nodepool.getHoldRequest(request_id)
            if not request:
                continue
            data.append(request.toDict())
        return data

    def autohold_info(self, hold_request_id):
        '''
        Get autohold request details.

        :param str hold_request_id: The unique ID of the request to delete.
        '''
        try:
            hold_request = self.zk_nodepool.getHoldRequest(hold_request_id)
        except Exception:
            self.log.exception(
                "Error retrieving autohold ID %s:", hold_request_id)
            return {}

        if hold_request is None:
            return {}
        return hold_request.toDict()

    def autohold_delete(self, hold_request_id):
        '''
        Delete an autohold request.

        :param str hold_request_id: The unique ID of the request to delete.
        '''
        hold_request = None
        try:
            hold_request = self.zk_nodepool.getHoldRequest(hold_request_id)
        except Exception:
            self.log.exception(
                "Error retrieving autohold ID %s:", hold_request_id)

        if not hold_request:
            self.log.info("Ignored request to remove invalid autohold ID %s",
                          hold_request_id)
            return

        self.log.debug("Removing autohold %s", hold_request)
        try:
            self.zk_nodepool.deleteHoldRequest(hold_request)
        except Exception:
            self.log.exception(
                "Error removing autohold request %s:", hold_request)

    def promote(self, tenant_name, pipeline_name, change_ids):
        event = PromoteEvent(tenant_name, pipeline_name, change_ids)
        result = self.management_events.put(event)
        self.log.debug("Waiting for promotion")
        result.wait()
        self.log.debug("Promotion complete")

    def dequeue(self, tenant_name, pipeline_name, project_name, change, ref):
        # We need to do some pre-processing here to get the correct
        # form of the project hostname and name based on un-known
        # inputs.
        tenant = self.abide.tenants.get(tenant_name)
        if tenant is None:
            raise ValueError(f'Unknown tenant {tenant_name}')
        (trusted, project) = tenant.getProject(project_name)
        if project is None:
            raise ValueError(f'Unknown project {project_name}')

        event = DequeueEvent(tenant_name, pipeline_name,
                             project.canonical_hostname, project.name,
                             change, ref)
        result = self.management_events.put(event)
        self.log.debug("Waiting for dequeue")
        result.wait()
        self.log.debug("Dequeue complete")

    def enqueue(self, tenant_name, pipeline_name, project_name,
                change, ref, oldrev, newrev):
        # We need to do some pre-processing here to get the correct
        # form of the project hostname and name based on un-known
        # inputs.
        tenant = self.abide.tenants.get(tenant_name)
        if tenant is None:
            raise ValueError(f'Unknown tenant {tenant_name}')
        (trusted, project) = tenant.getProject(project_name)
        if project is None:
            raise ValueError(f'Unknown project {project_name}')

        event = EnqueueEvent(tenant_name, pipeline_name,
                             project.canonical_hostname, project.name,
                             change, ref, oldrev, newrev)
        result = self.management_events.put(event)
        self.log.debug("Waiting for enqueue")
        result.wait()
        self.log.debug("Enqueue complete")

    def _get_time_database_dir(self):
        state_dir = get_default(self.config, 'scheduler', 'state_dir',
                                '/var/lib/zuul', expand_user=True)
        d = os.path.join(state_dir, 'times')
        if not os.path.exists(d):
            os.mkdir(d)
        return d

    def _get_key_store_password(self):
        try:
            return self.config["keystore"]["password"]
        except KeyError:
            raise RuntimeError("No key store password configured!")

    def _get_key_dir(self):
        state_dir = get_default(self.config, 'scheduler', 'state_dir',
                                '/var/lib/zuul', expand_user=True)
        key_dir = os.path.join(state_dir, 'keys')
        if not os.path.exists(key_dir):
            os.mkdir(key_dir, 0o700)
        st = os.stat(key_dir)
        mode = st.st_mode & 0o777
        if mode != 0o700:
            raise Exception("Project key directory %s must be mode 0700; "
                            "current mode is %o" % (key_dir, mode))
        return key_dir

    def _checkTenantSourceConf(self, config):
        tenant_config = None
        script = False
        if self.config.has_option(
            'scheduler', 'tenant_config'):
            tenant_config = self.config.get(
                'scheduler', 'tenant_config')
        if self.config.has_option(
            'scheduler', 'tenant_config_script'):
            if tenant_config:
                raise Exception(
                    "tenant_config and tenant_config_script options "
                    "are exclusive.")
            tenant_config = self.config.get(
                'scheduler', 'tenant_config_script')
            script = True
        if not tenant_config:
            raise Exception(
                "tenant_config or tenant_config_script option "
                "is missing from the configuration.")
        return tenant_config, script

    def _doReconfigureEvent(self, event):
        # This is called in the scheduler loop after another thread submits
        # a request
        self.layout_lock.acquire()
        self.config = self._zuul_app.config
        try:
            self.log.info("Full reconfiguration beginning")
            start = time.monotonic()

            # Reload the ansible manager in case the default ansible version
            # changed.
            default_ansible_version = get_default(
                self.config, 'scheduler', 'default_ansible_version', None)
            self.ansible_manager = AnsibleManager(
                default_version=default_ansible_version)

            for connection in self.connections.connections.values():
                self.log.debug("Clear cache for: %s" % connection)
                connection.clearCache()

            loader = configloader.ConfigLoader(
                self.connections, self, self.merger, self.keystore)
            tenant_config, script = self._checkTenantSourceConf(self.config)
            self.unparsed_abide = loader.readConfig(
                tenant_config, from_script=script)
            abide = loader.loadConfig(
                self.unparsed_abide, self.ansible_manager,
                event.validate_tenants)
            if event.validate_tenants is None:
                for tenant in abide.tenants.values():
                    self._reconfigureTenant(tenant)
                for old_tenant in self.abide.tenants.values():
                    if not abide.tenants.get(old_tenant.name):
                        # We deleted a tenant
                        self._reconfigureDeleteTenant(old_tenant)
                self.abide = abide
            else:
                loading_errors = []
                for tenant in abide.tenants.values():
                    for error in tenant.layout.loading_errors:
                        loading_errors.append(error.__repr__())
                if loading_errors:
                    summary = '\n\n\n'.join(loading_errors)
                    raise configloader.ConfigurationSyntaxError(
                        'Configuration errors: {}'.format(summary))
        finally:
            self.layout_lock.release()

        duration = round(time.monotonic() - start, 3)
        self.log.info("Full reconfiguration complete (duration: %s seconds)",
                      duration)

    def _doSmartReconfigureEvent(self, event):
        # This is called in the scheduler loop after another thread submits
        # a request
        reconfigured_tenants = []
        with self.layout_lock:
            self.config = self._zuul_app.config
            self.log.info("Smart reconfiguration beginning")
            start = time.monotonic()

            # Reload the ansible manager in case the default ansible version
            # changed.
            default_ansible_version = get_default(
                self.config, 'scheduler', 'default_ansible_version', None)
            self.ansible_manager = AnsibleManager(
                default_version=default_ansible_version)

            loader = configloader.ConfigLoader(
                self.connections, self, self.merger, self.keystore)
            tenant_config, script = self._checkTenantSourceConf(self.config)
            old_unparsed_abide = self.unparsed_abide
            self.unparsed_abide = loader.readConfig(
                tenant_config, from_script=script)

            # We need to handle new and deleted tenants so we need to process
            # all tenants from the currently known and the new ones.
            tenant_names = {t for t in self.abide.tenants}
            tenant_names.update(self.unparsed_abide.tenants.keys())
            for tenant_name in tenant_names:
                old_tenant = old_unparsed_abide.tenants.get(tenant_name)
                new_tenant = self.unparsed_abide.tenants.get(tenant_name)
                if old_tenant == new_tenant:
                    continue

                reconfigured_tenants.append(tenant_name)
                old_tenant = self.abide.tenants.get(tenant_name)
                if old_tenant is None:
                    # If there is no old tenant, use a fake tenant with the
                    # correct name
                    old_tenant = Tenant(tenant_name)
                abide = loader.reloadTenant(
                    self.abide, old_tenant, self.ansible_manager,
                    self.unparsed_abide)

                tenant = abide.tenants.get(tenant_name)
                if tenant is not None:
                    self._reconfigureTenant(tenant)
                else:
                    self._reconfigureDeleteTenant(old_tenant)
                self.abide = abide
        duration = round(time.monotonic() - start, 3)
        self.log.info("Smart reconfiguration of tenants %s complete "
                      "(duration: %s seconds)", reconfigured_tenants, duration)

    def _doTenantReconfigureEvent(self, event):
        # This is called in the scheduler loop after another thread submits
        # a request
        self.layout_lock.acquire()
        try:
            self.log.info("Tenant reconfiguration beginning for %s due to "
                          "projects %s",
                          event.tenant_name, event.project_branches)
            start = time.monotonic()
            # If a change landed to a project, clear out the cached
            # config of the changed branch before reconfiguring.
            for project_name, branch_name in event.project_branches:
                self.log.debug("Clearing unparsed config: %s @%s",
                               project_name, branch_name)
                self.abide.clearUnparsedBranchCache(project_name,
                                                    branch_name)
                with self.unparsed_config_cache.writeLock(project_name):
                    self.unparsed_config_cache.clearCache(project_name,
                                                          branch_name)

            old_tenant = self.abide.tenants[event.tenant_name]
            loader = configloader.ConfigLoader(
                self.connections, self, self.merger, self.keystore)
            abide = loader.reloadTenant(self.abide, old_tenant,
                                        self.ansible_manager,
                                        cache_ltime=event.zuul_event_ltime)
            tenant = abide.tenants[event.tenant_name]
            self._reconfigureTenant(tenant)
            self.abide = abide
        finally:
            self.layout_lock.release()
        duration = round(time.monotonic() - start, 3)
        self.log.info("Tenant reconfiguration complete for %s (duration: %s "
                      "seconds)", event.tenant_name, duration)

    def _reenqueueGetProject(self, tenant, item):
        project = item.change.project
        # Attempt to get the same project as the one passed in.  If
        # the project is now found on a different connection, return
        # the new version of the project.  If it is no longer
        # available (due to a connection being removed), return None.
        (trusted, new_project) = tenant.getProject(project.canonical_name)
        if new_project:
            return new_project

        if item.live:
            return None

        # If this is a non-live item we may be looking at a
        # "foreign" project, ie, one which is not defined in the
        # config but is constructed ad-hoc to satisfy a
        # cross-repo-dependency.  Find the corresponding live item
        # and use its source.
        child = item
        while child and not child.live:
            # This assumes that the queue does not branch behind this
            # item, which is currently true for non-live items; if
            # that changes, this traversal will need to be more
            # complex.
            if child.items_behind:
                child = child.items_behind[0]
            else:
                child = None
        if child is item:
            return None
        if child and child.live:
            (child_trusted, child_project) = tenant.getProject(
                child.change.project.canonical_name)
            if child_project:
                source = child_project.source
                new_project = source.getProject(project.name)
                return new_project

        return None

    def _reenqueueTenant(self, old_tenant, tenant):
        for name, new_pipeline in tenant.layout.pipelines.items():
            old_pipeline = old_tenant.layout.pipelines.get(name)
            if not old_pipeline:
                self.log.warning("No old pipeline matching %s found "
                                 "when reconfiguring" % name)
                continue
            self.log.debug("Re-enqueueing changes for pipeline %s" % name)
            # TODO(jeblair): This supports an undocument and
            # unanticipated hack to create a static window.  If we
            # really want to support this, maybe we should have a
            # 'static' type?  But it may be in use in the wild, so we
            # should allow this at least until there's an upgrade
            # path.
            if (new_pipeline.window and
                new_pipeline.window_increase_type == 'exponential' and
                new_pipeline.window_decrease_type == 'exponential' and
                new_pipeline.window_increase_factor == 1 and
                new_pipeline.window_decrease_factor == 1):
                static_window = True
            else:
                static_window = False
            if old_pipeline.window and (not static_window):
                new_pipeline.window = max(old_pipeline.window,
                                          new_pipeline.window_floor)
            items_to_remove = []
            builds_to_cancel = []
            requests_to_cancel = []
            for shared_queue in old_pipeline.queues:
                last_head = None
                # Attempt to keep window sizes from shrinking where possible
                project, branch = shared_queue.project_branches[0]
                new_queue = new_pipeline.getQueue(project, branch)
                if new_queue and shared_queue.window and (not static_window):
                    new_queue.window = max(shared_queue.window,
                                           new_queue.window_floor)
                for item in shared_queue.queue:
                    # If the old item ahead made it in, re-enqueue
                    # this one behind it.
                    new_project = self._reenqueueGetProject(
                        tenant, item)
                    if item.item_ahead in items_to_remove:
                        old_item_ahead = None
                        item_ahead_valid = False
                    else:
                        old_item_ahead = item.item_ahead
                        item_ahead_valid = True
                    item.item_ahead = None
                    item.items_behind = []
                    reenqueued = False
                    if new_project:
                        item.change.project = new_project
                        item.pipeline = None
                        item.queue = None
                        if not old_item_ahead or not last_head:
                            last_head = item
                        try:
                            reenqueued = new_pipeline.manager.reEnqueueItem(
                                item, last_head, old_item_ahead,
                                item_ahead_valid=item_ahead_valid)
                        except Exception:
                            self.log.exception(
                                "Exception while re-enqueing item %s",
                                item)
                    if reenqueued:
                        for build in item.current_build_set.getBuilds():
                            new_job = item.getJob(build.job.name)
                            if new_job:
                                build.job = new_job
                            else:
                                item.removeBuild(build)
                                builds_to_cancel.append(build)
                        for request_job, request in \
                            item.current_build_set.node_requests.items():
                            new_job = item.getJob(request_job)
                            if not new_job:
                                requests_to_cancel.append(
                                    (item.current_build_set, request))
                    else:
                        items_to_remove.append(item)
            for item in items_to_remove:
                self.log.info(
                    "Removing item %s during reconfiguration" % (item,))
                for build in item.current_build_set.getBuilds():
                    builds_to_cancel.append(build)
                for request_job, request in \
                    item.current_build_set.node_requests.items():
                    requests_to_cancel.append(
                        (item.current_build_set, request))

            for build in builds_to_cancel:
                self.log.info(
                    "Canceling build %s during reconfiguration" % (build,))
                self.cancelJob(build.build_set, build.job, build=build)
            for build_set, request in requests_to_cancel:
                self.log.info(
                    "Canceling node request %s during reconfiguration",
                    request)
                self.cancelJob(build_set, request.job)
        for name, old_pipeline in old_tenant.layout.pipelines.items():
            new_pipeline = tenant.layout.pipelines.get(name)
            if not new_pipeline:
                self._reconfigureDeletePipeline(old_pipeline)

    def _reconfigureTenant(self, tenant):
        # This is called from _doReconfigureEvent while holding the
        # layout lock
        old_tenant = self.abide.tenants.get(tenant.name)

        if old_tenant:
            self._reenqueueTenant(old_tenant, tenant)

        # TODOv3(jeblair): update for tenants
        # self.maintainConnectionCache()
        self.connections.reconfigureDrivers(tenant)

        # TODOv3(jeblair): remove postconfig calls?
        for pipeline in tenant.layout.pipelines.values():
            for trigger in pipeline.triggers:
                trigger.postConfig(pipeline)
            for reporter in pipeline.actions:
                reporter.postConfig()
        self.tenant_last_reconfigured[tenant.name] = time.time()
        if self.statsd:
            try:
                for pipeline in tenant.layout.pipelines.values():
                    items = len([x for x in pipeline.getAllItems() if x.live])
                    # stats.gauges.zuul.tenant.<tenant>.pipeline.
                    #    <pipeline>.current_changes
                    key = 'zuul.tenant.%s.pipeline.%s' % (
                        tenant.name, pipeline.name)
                    self.statsd.gauge(key + '.current_changes', items)
            except Exception:
                self.log.exception("Exception reporting initial "
                                   "pipeline stats:")

    def _reconfigureDeleteTenant(self, tenant):
        # Called when a tenant is deleted during reconfiguration
        self.log.info("Removing tenant %s during reconfiguration" %
                      (tenant,))
        for pipeline in tenant.layout.pipelines.values():
            self._reconfigureDeletePipeline(pipeline)

        # Delete the tenant root path for this tenant in ZooKeeper to remove
        # all tenant specific event queues
        try:
            self.zk_client.client.delete(f"{TENANT_ROOT}/{tenant.name}",
                                         recursive=True)
        except NotEmptyError:
            # In case a build result has been submitted during the
            # reconfiguration, this cleanup will fail. We handle this in a
            # periodic cleanup job.
            pass

    def _reconfigureDeletePipeline(self, pipeline):
        self.log.info("Removing pipeline %s during reconfiguration" %
                      (pipeline,))
        for shared_queue in pipeline.queues:
            builds_to_cancel = []
            requests_to_cancel = []
            for item in shared_queue.queue:
                item.item_ahead = None
                item.items_behind = []
                self.log.info(
                    "Removing item %s during reconfiguration" % (item,))
                for build in item.current_build_set.getBuilds():
                    builds_to_cancel.append(build)
                for request_job, request in \
                    item.current_build_set.node_requests.items():
                    requests_to_cancel.append(
                        (item.current_build_set, request))

            for build in builds_to_cancel:
                self.log.info(
                    "Canceling build %s during reconfiguration" % (build,))
                self.cancelJob(build.build_set, build.job,
                               build=build, force=True)
            for build_set, request in requests_to_cancel:
                self.log.info(
                    "Canceling node request %s during reconfiguration",
                    request)
                self.cancelJob(build_set, request.job, force=True)

    def _doPromoteEvent(self, event):
        tenant = self.abide.tenants.get(event.tenant_name)
        pipeline = tenant.layout.pipelines[event.pipeline_name]
        change_ids = [c.split(',') for c in event.change_ids]
        items_to_enqueue = []
        change_queue = None
        for shared_queue in pipeline.queues:
            if change_queue:
                break
            for item in shared_queue.queue:
                if (item.change.number == change_ids[0][0] and
                        item.change.patchset == change_ids[0][1]):
                    change_queue = shared_queue
                    break
        if not change_queue:
            raise Exception("Unable to find shared change queue for %s" %
                            event.change_ids[0])
        for number, patchset in change_ids:
            found = False
            for item in change_queue.queue:
                if (item.change.number == number and
                        item.change.patchset == patchset):
                    found = True
                    items_to_enqueue.append(item)
                    break
            if not found:
                raise Exception("Unable to find %s,%s in queue %s" %
                                (number, patchset, change_queue))
        for item in change_queue.queue[:]:
            if item not in items_to_enqueue:
                items_to_enqueue.append(item)
            pipeline.manager.cancelJobs(item)
            pipeline.manager.dequeueItem(item)
        for item in items_to_enqueue:
            pipeline.manager.addChange(
                item.change, event,
                enqueue_time=item.enqueue_time,
                quiet=True,
                ignore_requirements=True)

    def _doDequeueEvent(self, event):
        tenant = self.abide.tenants.get(event.tenant_name)
        if tenant is None:
            raise ValueError('Unknown tenant %s' % event.tenant_name)
        pipeline = tenant.layout.pipelines.get(event.pipeline_name)
        if pipeline is None:
            raise ValueError('Unknown pipeline %s' % event.pipeline_name)
        canonical_name = event.project_hostname + '/' + event.project_name
        (trusted, project) = tenant.getProject(canonical_name)
        if project is None:
            raise ValueError('Unknown project %s' % event.project_name)
        change = project.source.getChange(event)
        if change.project.name != project.name:
            if event.change:
                item = 'Change %s' % event.change
            else:
                item = 'Ref %s' % event.ref
            raise Exception('%s does not belong to project "%s"'
                            % (item, project.name))
        for shared_queue in pipeline.queues:
            for item in shared_queue.queue:
                if item.change.project != change.project:
                    continue
                if (isinstance(item.change, model.Change) and
                        item.change.number == change.number and
                        item.change.patchset == change.patchset) or\
                   (item.change.ref == change.ref):
                    pipeline.manager.removeItem(item)
                    return
        raise Exception("Unable to find shared change queue for %s:%s" %
                        (event.project_name,
                         event.change or event.ref))

    def _doEnqueueEvent(self, event):
        tenant = self.abide.tenants.get(event.tenant_name)
        if tenant is None:
            raise ValueError(f'Unknown tenant {event.tenant_name}')
        pipeline = tenant.layout.pipelines.get(event.pipeline_name)
        if pipeline is None:
            raise ValueError(f'Unknown pipeline {event.pipeline_name}')
        canonical_name = event.project_hostname + '/' + event.project_name
        (trusted, project) = tenant.getProject(canonical_name)
        if project is None:
            raise ValueError(f'Unknown project {event.project_name}')
        try:
            change = project.source.getChange(event, refresh=True)
        except Exception as exc:
            raise ValueError('Unknown change') from exc

        if change.project.name != project.name:
            raise Exception(
                f'Change {change} does not belong to project "{project.name}"')
        self.log.debug("Event %s for change %s was directly assigned "
                       "to pipeline %s", event, change, self)
        pipeline.manager.addChange(change, event, ignore_requirements=True)

    def _areAllBuildsComplete(self):
        self.log.debug("Checking if all builds are complete")
        if self.merger.areMergesOutstanding():
            self.log.debug("Waiting on merger")
            return False
        waiting = False
        for tenant in self.abide.tenants.values():
            for pipeline in tenant.layout.pipelines.values():
                for item in pipeline.getAllItems():
                    for build in item.current_build_set.getBuilds():
                        if build.result is None:
                            self.log.debug("%s waiting on %s" %
                                           (pipeline.manager, build))
                            waiting = True
        if not waiting:
            self.log.debug("All builds are complete")
            return True
        return False

    def run(self):
        if self.statsd:
            self.log.debug("Statsd enabled")
        else:
            self.log.debug("Statsd not configured")
        while True:
            self.log.debug("Run handler sleeping")
            self.wake_event.wait()
            self.wake_event.clear()
            if self._stopped:
                self.log.debug("Run handler stopping")
                return
            self.log.debug("Run handler awake")
            self.run_handler_lock.acquire()
            try:
                if not self._stopped:
                    self.process_global_management_queue()

                if not self._stopped:
                    self.process_management_queue()

                # Give result events priority -- they let us stop builds,
                # whereas trigger events cause us to execute builds.
                if not self._stopped:
                    self.process_result_queue()

                if not self._stopped:
                    self.process_global_trigger_queue()

                if not self._stopped:
                    self.process_trigger_queue()

                for tenant in self.abide.tenants.values():
                    for pipeline in tenant.layout.pipelines.values():
                        try:
                            while (pipeline.manager.processQueue() and
                                   not self._stopped):
                                pass
                        except Exception:
                            self.log.exception(
                                "Exception in pipeline processing:")
                            pipeline.state = pipeline.STATE_ERROR
                            # Continue processing other pipelines+tenants
                        else:
                            pipeline.state = pipeline.STATE_NORMAL
            except Exception:
                self.log.exception("Exception in run handler:")
                # There may still be more events to process
                self.wake_event.set()
            finally:
                self.run_handler_lock.release()

    def maintainConnectionCache(self):
        # TODOv3(jeblair): update for tenants
        relevant = set()
        for tenant in self.abide.tenants.values():
            for pipeline in tenant.layout.pipelines.values():
                self.log.debug("Gather relevant cache items for: %s" %
                               pipeline)

                for item in pipeline.getAllItems():
                    relevant.add(item.change)
                    relevant.update(item.change.getRelatedChanges())
        for connection in self.connections.values():
            connection.maintainCache(relevant)
            self.log.debug(
                "End maintain connection cache for: %s" % connection)
        self.log.debug("Connection cache size: %s" % len(relevant))

    def process_global_trigger_queue(self):
        for event in self.trigger_events:
            log = get_annotated_logger(self.log, event.zuul_event_id)
            log.debug("Forwarding trigger event %s", event)
            try:
                for tenant in self.abide.tenants.values():
                    try:
                        self._forward_trigger_event(event, tenant)
                    except Exception:
                        log.exception("Unable to forward event %s "
                                      "to tenant %s", event, tenant.name)
            finally:
                self.trigger_events.ack(event)

    def _forward_trigger_event(self, event, tenant):
        log = get_annotated_logger(self.log, event.zuul_event_id)
        trusted, project = tenant.getProject(event.canonical_project_name)

        if project is None:
            return

        try:
            change = project.source.getChange(event)
        except exceptions.ChangeNotFound as e:
            log.debug("Unable to get change %s from source %s",
                      e.change, project.source)
            return

        reconfigure_tenant = False
        if ((event.branch_updated and
             hasattr(change, 'files') and
             change.updatesConfig(tenant)) or
            (event.branch_deleted and
             self.abide.hasUnparsedBranchCache(project.canonical_name,
                                               event.branch))):
            reconfigure_tenant = True

        # The branch_created attribute is also true when a tag is
        # created. Since we load config only from branches only trigger
        # a tenant reconfiguration if the branch is set as well.
        if event.branch_created and event.branch:
            reconfigure_tenant = True

        # If the driver knows the branch but we don't have a config, we
        # also need to reconfigure. This happens if a GitHub branch
        # was just configured as protected without a push in between.
        if (event.branch in project.source.getProjectBranches(
                project, tenant)
            and not self.abide.hasUnparsedBranchCache(
                project.canonical_name, event.branch)):
            reconfigure_tenant = True

        # If the branch is unprotected and unprotected branches
        # are excluded from the tenant for that project skip reconfig.
        if (reconfigure_tenant and not
            event.branch_protected and
            tenant.getExcludeUnprotectedBranches(project)):

            reconfigure_tenant = False

        if reconfigure_tenant:
            # The change that just landed updates the config
            # or a branch was just created or deleted.  Clear
            # out cached data for this project and perform a
            # reconfiguration.
            self.reconfigureTenant(tenant, change.project, event)

        for pipeline in tenant.layout.pipelines.values():
            if (
                pipeline.manager.eventMatches(event, change)
                or pipeline.manager.isChangeAlreadyInPipeline(change)
                or pipeline.manager.findOldVersionOfChangeAlreadyInQueue(
                    change
                )
            ):
                self.pipeline_trigger_events[tenant.name][
                    pipeline.name
                ].put(event.driver_name, event)

    def process_trigger_queue(self):
        for tenant in self.abide.tenants.values():
            for pipeline in tenant.layout.pipelines.values():
                for event in self.pipeline_trigger_events[tenant.name][
                    pipeline.name
                ]:
                    if self._stopped:
                        return
                    log = get_annotated_logger(
                        self.log, event.zuul_event_id
                    )
                    log.debug("Processing trigger event %s", event)
                    try:
                        self._process_trigger_event(tenant, pipeline, event)
                    finally:
                        self.pipeline_trigger_events[tenant.name][
                            pipeline.name
                        ].ack(event)

    def _process_trigger_event(self, tenant, pipeline, event):
        log = get_annotated_logger(
            self.log, event.zuul_event_id
        )
        trusted, project = tenant.getProject(event.canonical_project_name)
        if project is None:
            return
        try:
            change = project.source.getChange(event)
        except exceptions.ChangeNotFound as e:
            log.debug("Unable to get change %s from source %s",
                      e.change, project.source)
            return

        if event.isPatchsetCreated():
            pipeline.manager.removeOldVersionsOfChange(
                change, event)
        elif event.isChangeAbandoned():
            pipeline.manager.removeAbandonedChange(change, event)
        if pipeline.manager.eventMatches(event, change):
            pipeline.manager.addChange(change, event)

    def process_global_management_queue(self):
        for event in self.management_events:
            event_forwarded = False
            try:
                if isinstance(event, ReconfigureEvent):
                    self._doReconfigureEvent(event)
                elif isinstance(event, SmartReconfigureEvent):
                    self._doSmartReconfigureEvent(event)
                elif isinstance(event, TenantReconfigureEvent):
                    self._doTenantReconfigureEvent(event)
                elif isinstance(event, (PromoteEvent, ChangeManagementEvent)):
                    event_forwarded = self._forward_management_event(event)
                else:
                    self.log.error("Unable to handle event %s", event)
            finally:
                if event_forwarded:
                    self.management_events.ackWithoutResult(event)
                else:
                    self.management_events.ack(event)

    def _forward_management_event(self, event):
        event_forwarded = False
        try:
            tenant = self.abide.tenants.get(event.tenant_name)
            if tenant is None:
                raise ValueError(f'Unknown tenant {event.tenant_name}')
            pipeline = tenant.layout.pipelines.get(event.pipeline_name)
            if pipeline is None:
                raise ValueError(f'Unknown pipeline {event.pipeline_name}')
            self.pipeline_management_events[tenant.name][
                pipeline.name
            ].put(event)
            event_forwarded = True
        except Exception:
            event.exception(
                "".join(
                    traceback.format_exception(*sys.exc_info())
                )
            )
        return event_forwarded

    def process_management_queue(self):
        for tenant in self.abide.tenants.values():
            for pipeline in tenant.layout.pipelines.values():
                for event in self.pipeline_management_events[tenant.name][
                    pipeline.name
                ]:
                    if self._stopped:
                        return
                    log = get_annotated_logger(
                        self.log, event.zuul_event_id
                    )
                    log.debug("Processing management event %s", event)
                    try:
                        self._process_management_event(event)
                    finally:
                        self.pipeline_management_events[tenant.name][
                            pipeline.name
                        ].ack(event)

    def _process_management_event(self, event):
        try:
            if isinstance(event, PromoteEvent):
                self._doPromoteEvent(event)
            elif isinstance(event, DequeueEvent):
                self._doDequeueEvent(event)
            elif isinstance(event, EnqueueEvent):
                self._doEnqueueEvent(event)
            else:
                self.log.error("Unable to handle event %s" % event)
        except Exception:
            self.log.exception("Exception in management event:")
            event.exception(
                "".join(traceback.format_exception(*sys.exc_info()))
            )

    def process_result_queue(self):
        for tenant in self.abide.tenants.values():
            for pipeline in tenant.layout.pipelines.values():
                for event in self.pipeline_result_events[tenant.name][
                    pipeline.name
                ]:
                    if self._stopped:
                        return
                    self.log.debug(
                        "Processing result event %s for build %s",
                        event,
                        event.build,
                    )
                    try:
                        self._process_result_event(event)
                    finally:
                        self.pipeline_result_events[tenant.name][
                            pipeline.name
                        ].ack(event)

        # TODO (felix): The old result event queue is still used for the merge
        # results and will be removed once we switch the merge jobs to ZK as
        # well.
        while not self.result_event_queue.empty() and not self._stopped:
            self.log.debug("Fetching result event")
            event = self.result_event_queue.get()
            try:
                if isinstance(event, MergeCompletedEvent):
                    self._doMergeCompletedEvent(event)
                elif isinstance(event, FilesChangesCompletedEvent):
                    self._doFilesChangesCompletedEvent(event)
                elif isinstance(event, NodesProvisionedEvent):
                    self._doNodesProvisionedEvent(event)
                else:
                    self.log.error("Unable to handle event %s", event)
            finally:
                self.result_event_queue.task_done()

    def _process_result_event(self, event):
        if isinstance(event, BuildStartedEvent):
            self._doBuildStartedEvent(event)
        elif isinstance(event, BuildStatusEvent):
            self._doBuildStatusEvent(event)
        elif isinstance(event, BuildPausedEvent):
            self._doBuildPausedEvent(event)
        elif isinstance(event, BuildCompletedEvent):
            self._doBuildCompletedEvent(event)
        else:
            self.log.error("Unable to handle event %s", event)

    def _doBuildStartedEvent(self, event):
        build = self.executor.builds.get(event.build)
        if not build:
            return

        build.start_time = event.data["start_time"]
        # TODO (felix): Remove this once the builds are executed via ZooKeeper.
        # It's currently necessary to set the correct private attribute on the
        # build for the gearman worker.
        self.executor.setWorkerInfo(build, event.data)

        log = get_annotated_logger(self.log, build.zuul_event_id)
        if build.build_set is not build.build_set.item.current_build_set:
            log.warning("Build %s is not in the current build set", build)
            return
        pipeline = build.build_set.item.pipeline
        if not pipeline:
            log.warning("Build %s is not associated with a pipeline", build)
            return
        try:
            build.estimated_time = float(self.time_database.getEstimatedTime(
                build))
        except Exception:
            log.exception("Exception estimating build time:")
        pipeline.manager.onBuildStarted(build)

    def _doBuildStatusEvent(self, event):
        build = self.executor.builds.get(event.build)
        if not build:
            return

        # Allow URL to be updated
        build.url = event.data.get('url', build.url)

    def _doBuildPausedEvent(self, event):
        build = self.executor.builds.get(event.build)
        if not build:
            return

        # Setting paused is deferred to event processing stage to avoid a race
        # with child job skipping.
        build.paused = True
        build.result_data = event.data.get("data", {})

        log = get_annotated_logger(self.log, build.zuul_event_id)
        if build.build_set is not build.build_set.item.current_build_set:
            log.warning("Build %s is not in the current build set", build)
            try:
                self.executor.cancel(build)
            except Exception:
                log.exception(
                    "Exception while canceling paused build %s", build)
            return
        pipeline = build.build_set.item.pipeline
        if not pipeline:
            log.warning("Build %s is not associated with a pipeline", build)
            try:
                self.executor.cancel(build)
            except Exception:
                log.exception(
                    "Exception while canceling paused build %s", build)
            return
        pipeline.manager.onBuildPaused(build)

    def _handleExpiredHoldRequest(self, request):
        '''
        Check if a hold request is expired and delete it if it is.

        The 'expiration' attribute will be set to the clock time when the
        hold request was used for the last time. If this is NOT set, then
        the request is still active.

        If a node expiration time is set on the request, and the request is
        expired, *and* we've waited for a defined period past the node
        expiration (EXPIRED_HOLD_REQUEST_TTL), then we will delete the hold
        request.

        :returns: True if it is expired, False otherwise.
        '''
        if not request.expired:
            return False

        if not request.node_expiration:
            # Request has been used up but there is no node expiration, so
            # we don't auto-delete it.
            return True

        elapsed = time.time() - request.expired
        if elapsed < self.EXPIRED_HOLD_REQUEST_TTL + request.node_expiration:
            # Haven't reached our defined expiration lifetime, so don't
            # auto-delete it yet.
            return True

        try:
            self.zk_nodepool.lockHoldRequest(request)
            self.log.info("Removing expired hold request %s", request)
            self.zk_nodepool.deleteHoldRequest(request)
        except Exception:
            self.log.exception(
                "Failed to delete expired hold request %s", request)
        finally:
            try:
                self.zk_nodepool.unlockHoldRequest(request)
            except Exception:
                pass

        return True

    def _getAutoholdRequest(self, build):
        change = build.build_set.item.change

        autohold_key_base = (build.pipeline.tenant.name,
                             change.project.canonical_name,
                             build.job.name)

        class Scope(object):
            """Enum defining a precedence/priority of autohold requests.

            Autohold requests for specific refs should be fulfilled first,
            before those for changes, and generic jobs.

            Matching algorithm goes over all existing autohold requests, and
            returns one with the highest number (in case of duplicated
            requests the last one wins).
            """
            NONE = 0
            JOB = 1
            CHANGE = 2
            REF = 3

        # Do a partial match of the autohold key against all autohold
        # requests, ignoring the last element of the key (ref filter),
        # and finally do a regex match between ref filter from
        # the autohold request and the build's change ref to check
        # if it matches. Lastly, make sure that we match the most
        # specific autohold request by comparing "scopes"
        # of requests - the most specific is selected.
        autohold = None
        scope = Scope.NONE
        self.log.debug("Checking build autohold key %s", autohold_key_base)
        for request_id in self.zk_nodepool.getHoldRequests():
            request = self.zk_nodepool.getHoldRequest(request_id)
            if not request:
                continue

            if self._handleExpiredHoldRequest(request):
                continue

            ref_filter = request.ref_filter

            if request.current_count >= request.max_count:
                # This request has been used the max number of times
                continue
            elif not (request.tenant == autohold_key_base[0] and
                      request.project == autohold_key_base[1] and
                      request.job == autohold_key_base[2]):
                continue
            elif not re.match(ref_filter, change.ref):
                continue

            if ref_filter == ".*":
                candidate_scope = Scope.JOB
            elif ref_filter.endswith(".*"):
                candidate_scope = Scope.CHANGE
            else:
                candidate_scope = Scope.REF

            self.log.debug("Build autohold key %s matched scope %s",
                           autohold_key_base, candidate_scope)
            if candidate_scope > scope:
                scope = candidate_scope
                autohold = request

        return autohold

    def _processAutohold(self, build):
        # We explicitly only want to hold nodes for jobs if they have
        # failed / retry_limit / post_failure and have an autohold request.
        hold_list = ["FAILURE", "RETRY_LIMIT", "POST_FAILURE", "TIMED_OUT"]
        if build.result not in hold_list:
            return False

        request = self._getAutoholdRequest(build)
        if request is not None:
            self.log.debug("Got autohold %s", request)
            self.nodepool.holdNodeSet(build.nodeset, request, build)
            return True
        return False

    def _doBuildCompletedEvent(self, event):
        # Get the local build object from the executor client
        build = self.executor.builds.get(event.build)
        if not build:
            self.log.error("Unable to find build %s", event.build)
            return

        log = get_annotated_logger(
            self.log, event=build.zuul_event_id, build=build.uuid
        )
        event_result = event.result

        build.node_labels = event_result.get("node_labels", [])
        build.node_name = event_result.get("node_name")
        result = event_result.get("result")
        build.error_detail = event_result.get("error_detail")

        if result is None:
            if (
                build.build_set.getTries(build.job.name) >= build.job.attempts
            ):
                result = "RETRY_LIMIT"
            else:
                build.retry = True
        if result in ("DISCONNECT", "ABORTED"):
            # Always retry if the executor just went away
            build.retry = True
        if result == "MERGER_FAILURE":
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
            if (
                build.build_set.getTries(build.job.name) < build.job.attempts
            ):
                build.retry = True

        result_data = event_result.get("data", {})
        warnings = event_result.get("warnings", [])

        log.info("Build complete, result %s, warnings %s", result, warnings)

        if build.retry:
            result = "RETRY"

        # If the build was canceled, we did actively cancel the job so
        # don't overwrite the result and don't retry.
        if build.canceled:
            result = build.result
            build.retry = False

        build.end_time = event_result["end_time"]
        build.result_data = result_data
        build.build_set.warning_messages.extend(warnings)

        build.result = result
        self._reportBuildStats(build)

        # Regardless of any other conditions which might cause us not
        # to pass this on to the pipeline manager, make sure we return
        # the nodes to nodepool.
        try:
            build.held = self._processAutohold(build)
            self.log.debug(
                'build "%s" held status set to %s', build, build.held
            )
        except Exception:
            log.exception("Unable to process autohold for %s", build)
        try:
            self.nodepool.returnNodeSet(build.nodeset, build=build,
                                        zuul_event_id=build.zuul_event_id)
        except Exception:
            log.exception("Unable to return nodeset %s" % build.nodeset)

        # The test suite expects the build to be removed from the
        # internal dict after it's added to the report queue.
        del self.executor.builds[build.uuid]

        if build.build_set is not build.build_set.item.current_build_set:
            log.debug("Build %s is not in the current build set", build)
            return
        pipeline = build.build_set.item.pipeline
        if not pipeline:
            log.warning("Build %s is not associated with a pipeline", build)
            return
        if build.end_time and build.start_time and build.result:
            duration = build.end_time - build.start_time
            try:
                self.time_database.update(build, duration, build.result)
            except Exception:
                log.exception("Exception recording build time:")

        pipeline.manager.onBuildCompleted(build)

    def _doMergeCompletedEvent(self, event):
        build_set = event.build_set
        if build_set is not build_set.item.current_build_set:
            self.log.warning("Build set %s is not current" % (build_set,))
            return
        pipeline = build_set.item.pipeline
        if not pipeline:
            self.log.warning("Build set %s is not associated with a pipeline" %
                             (build_set,))
            return
        pipeline.manager.onMergeCompleted(event)

    def _doFilesChangesCompletedEvent(self, event):
        build_set = event.build_set
        if build_set is not build_set.item.current_build_set:
            self.log.warning("Build set %s is not current", build_set)
            return
        pipeline = build_set.item.pipeline
        if not pipeline:
            self.log.warning("Build set %s is not associated with a pipeline",
                             build_set)
            return
        pipeline.manager.onFilesChangesCompleted(event)

    def _doNodesProvisionedEvent(self, event):
        request = event.request
        request_id = event.request_id
        build_set = request.build_set
        log = get_annotated_logger(self.log, request.event_id)

        ready = self.nodepool.acceptNodes(request, request_id)
        if not ready:
            return

        if build_set is not build_set.item.current_build_set:
            log.warning("Build set %s is not current "
                        "for node request %s", build_set, request)
            if request.fulfilled:
                self.nodepool.returnNodeSet(request.nodeset,
                                            zuul_event_id=request.event_id)
            return
        if request.job.name not in [x.name for x in build_set.item.getJobs()]:
            log.warning("Item %s does not contain job %s "
                        "for node request %s",
                        build_set.item, request.job.name, request)
            build_set.removeJobNodeRequest(request.job.name)
            if request.fulfilled:
                self.nodepool.returnNodeSet(request.nodeset,
                                            zuul_event_id=request.event_id)
            return
        pipeline = build_set.item.pipeline
        if not pipeline:
            log.warning("Build set %s is not associated with a pipeline "
                        "for node request %s", build_set, request)
            if request.fulfilled:
                self.nodepool.returnNodeSet(request.nodeset,
                                            zuul_event_id=request.event_id)
            return
        pipeline.manager.onNodesProvisioned(event)

    def formatStatusJSON(self, tenant_name):
        # TODOv3(jeblair): use tenants
        data = {}

        data['zuul_version'] = self.zuul_version
        websocket_url = get_default(self.config, 'web', 'websocket_url', None)

        data['trigger_event_queue'] = {}
        data['trigger_event_queue']['length'] = len(self.trigger_events)
        data['result_event_queue'] = {}
        data['result_event_queue']['length'] = \
            self.result_event_queue.qsize()
        data['management_event_queue'] = {}
        data['management_event_queue']['length'] = len(self.management_events)
        data['connection_event_queues'] = {}
        for connection in self.connections.connections.values():
            queue = connection.getEventQueue()
            if queue is not None:
                data['connection_event_queues'][connection.connection_name] = {
                    'length': len(queue),
                }

        if self.last_reconfigured:
            data['last_reconfigured'] = self.last_reconfigured * 1000

        pipelines = []
        data['pipelines'] = pipelines
        tenant = self.abide.tenants.get(tenant_name)
        if not tenant:
            if tenant_name not in self.unparsed_abide.tenants:
                return json.dumps({
                    "message": "Unknown tenant",
                    "code": 404
                })
            self.log.warning("Tenant %s isn't loaded" % tenant_name)
            return json.dumps({
                "message": "Tenant %s isn't ready" % tenant_name,
                "code": 204
            })
        trigger_event_queues = self.pipeline_trigger_events[tenant_name]
        result_event_queues = self.pipeline_result_events[tenant_name]
        management_event_queues = self.pipeline_management_events[tenant_name]
        for pipeline in tenant.layout.pipelines.values():
            status = pipeline.formatStatusJSON(websocket_url)
            status['trigger_events'] = len(
                trigger_event_queues[pipeline.name])
            status['result_events'] = len(
                result_event_queues[pipeline.name])
            status['management_events'] = len(
                management_event_queues[pipeline.name])
            pipelines.append(status)
        return json.dumps(data)

    def onChangeUpdated(self, change, event):
        """Remove stale dependency references on change update.

        When a change is updated with a new patchset, other changes in
        the system may still have a reference to the old patchset in
        their dependencies.  Search for those (across all sources) and
        mark that their dependencies are out of date.  This will cause
        them to be refreshed the next time the queue processor
        examines them.
        """
        log = get_annotated_logger(self.log, event)
        log.debug("Change %s has been updated, clearing dependent "
                  "change caches", change)
        for source in self.connections.getSources():
            for other_change in source.getCachedChanges():
                if other_change.commit_needs_changes is None:
                    continue
                for dep in other_change.commit_needs_changes:
                    if change.isUpdateOf(dep):
                        other_change.refresh_deps = True
        change.refresh_deps = True

    def cancelJob(self, buildset, job, build=None, final=False,
                  force=False):
        """Cancel a running build

        Set final to true to create a fake build result even if the
        job has not run.  TODO: explain this better.

        Set force to true to forcibly release build resources without
        waiting for a result from the executor.  Use this when
        removing pipelines.

        """
        item = buildset.item
        log = get_annotated_logger(self.log, item.event)
        job_name = job.name
        try:
            # Cancel node request if needed
            req = buildset.getJobNodeRequest(job_name)
            if req:
                self.nodepool.cancelRequest(req)
                buildset.removeJobNodeRequest(job_name)

            # Cancel build if needed
            build = build or buildset.getBuild(job_name)
            if build:
                was_running = False
                try:
                    was_running = self.executor.cancel(build)
                except Exception:
                    log.exception(
                        "Exception while canceling build %s for change %s",
                        build, item.change)

                if (not was_running) or force:
                    nodeset = buildset.getJobNodeSet(job_name)
                    if nodeset:
                        self.nodepool.returnNodeSet(
                            nodeset, build=build, zuul_event_id=item.event)

                # In the unlikely case that a build is removed and
                # later added back, make sure we clear out the nodeset
                # so it gets requested again.
                try:
                    buildset.removeJobNodeSet(job_name)
                except Exception:
                    log.exception(
                        "Exception while removing nodeset from build %s "
                        "for change %s", build, build.build_set.item.change)

                if build.result is None:
                    build.result = 'CANCELED'

                if force:
                    # Directly delete the build rather than putting a
                    # CANCELED event in the result event queue since
                    # the result event queue won't be processed
                    # anymore once the pipeline is removed.
                    try:
                        del self.executor.builds[build.uuid]
                    except KeyError:
                        pass
            else:
                nodeset = buildset.getJobNodeSet(job_name)
                if nodeset:
                    self.nodepool.returnNodeSet(
                        nodeset, zuul_event_id=item.event)

                if final:
                    # If final is set make sure that the job is not resurrected
                    # later by re-requesting nodes.
                    fakebuild = Build(job, item.current_build_set, None)
                    fakebuild.result = 'CANCELED'
                    buildset.addBuild(fakebuild)
        finally:
            # Release the semaphore in any case
            tenant = buildset.item.pipeline.tenant
            tenant.semaphore_handler.release(item, job)
