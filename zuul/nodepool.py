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
import threading
import time

from collections import defaultdict
from zuul import model
from zuul.lib.logutil import get_annotated_logger
from zuul.zk.event_queues import (
    PipelineResultEventQueue,
    NodepoolEventElection
)
from zuul.zk.exceptions import LockException
from zuul.zk.nodepool import NodeRequestEvent, ZooKeeperNodepool


def add_resources(target, source):
    for key, value in source.items():
        target[key] += value


def subtract_resources(target, source):
    for key, value in source.items():
        target[key] -= value


class Nodepool(object):
    log = logging.getLogger('zuul.nodepool')

    def __init__(self, zk_client, system_id, statsd, scheduler=False):
        self._stopped = False
        self.system_id = system_id
        self.statsd = statsd

        self.election_won = False
        if scheduler:
            # Only enable the node request cache/callback for the scheduler.
            self.stop_watcher_event = threading.Event()
            self.zk_nodepool = ZooKeeperNodepool(
                zk_client,
                enable_node_request_cache=True,
                node_request_event_callback=self._handleNodeRequestEvent)
            self.election = NodepoolEventElection(zk_client)
            self.event_thread = threading.Thread(target=self.runEventElection)
            self.event_thread.daemon = True
            self.event_thread.start()
        else:
            self.stop_watcher_event = None
            self.zk_nodepool = ZooKeeperNodepool(zk_client)
            self.election = None
            self.event_thread = None

        self.pipeline_result_events = PipelineResultEventQueue.createRegistry(
            zk_client
        )

        # TODO: remove internal caches for SOS
        self.requests = {}
        self.current_resources_by_tenant = {}
        self.current_resources_by_project = {}

    def runEventElection(self):
        while not self._stopped:
            try:
                self.log.debug("Running nodepool watcher election")
                self.election.run(self._electionWon)
            except Exception:
                self.log.exception("Error in nodepool watcher:")

    def stop(self):
        self.log.debug("Stopping")
        self._stopped = True
        if self.election:
            self.election.cancel()
            self.stop_watcher_event.set()
            self.event_thread.join()
            # Delete the election to avoid a FD leak in tests.
            del self.election

    def _sendNodesProvisionedEvent(self, request):
        tenant_name = request.tenant_name
        pipeline_name = request.pipeline_name
        event = model.NodesProvisionedEvent(
            request.id, request.job_name, request.build_set_uuid)
        self.pipeline_result_events[tenant_name][pipeline_name].put(event)

    def _electionWon(self):
        self.log.info("Watching nodepool requests")
        # Iterate over every completed request in case we are starting
        # up or missed something in the transition.
        self.election_won = True
        try:
            for rid in self.zk_nodepool.getNodeRequests():
                request = self.zk_nodepool.getNodeRequest(rid)
                if request.requestor != self.system_id:
                    continue
                if (request.state in {model.STATE_FULFILLED,
                                      model.STATE_FAILED}):
                    self._sendNodesProvisionedEvent(request)
            # Now resume normal event processing.
            self.stop_watcher_event.wait()
        finally:
            self.stop_watcher_event.clear()
            self.election_won = False

    def _handleNodeRequestEvent(self, request, event, request_id=None):
        # TODO (felix): This callback should be wrapped by leader election, so
        # that only one scheduler puts NodesProvisionedEvents in the queue.
        log = get_annotated_logger(self.log, event=request.event_id)

        if request.requestor != self.system_id:
            return

        if request.uid not in self.requests:
            log.debug("Node request %s is unknown", request)
            return

        log.debug("Node request %s %s", request, request.state)
        if event == NodeRequestEvent.COMPLETED:
            # This sequence is required for tests -- we can only
            # remove the request from our internal cache after the
            # completed event is added to the zk queue.
            try:
                if self.election_won:
                    self.emitStats(request)
                    self._sendNodesProvisionedEvent(request)
            except Exception:
                # If there are any errors moving the event, re-run the
                # election.
                if self.stop_watcher_event is not None:
                    self.stop_watcher_event.set()
                raise
            del self.requests[request.uid]
        elif event == NodeRequestEvent.DELETED:
            # Presumably we already removed it when it was complete.
            req = self.requests.pop(request.uid, None)
            if req is not None:
                self.log.error("Node request %s was removed out of band",
                               request)

    def emitStats(self, request):
        # Implements the following :
        #  counter zuul.nodepool.requests.<state>.total
        #  counter zuul.nodepool.requests.<state>.label.<label>
        #  counter zuul.nodepool.requests.<state>.size.<size>
        #  timer   zuul.nodepool.requests.(fulfilled|failed)
        #  timer   zuul.nodepool.requests.(fulfilled|failed).<label>
        #  timer   zuul.nodepool.requests.(fulfilled|failed).<size>
        if not self.statsd:
            return
        pipe = self.statsd.pipeline()
        state = request.state
        dt = None

        if request.canceled:
            state = 'canceled'
        elif request.state in (model.STATE_FULFILLED, model.STATE_FAILED):
            dt = int((request.state_time - request.requested_time) * 1000)

        key = 'zuul.nodepool.requests.%s' % state
        pipe.incr(key + ".total")

        if dt:
            pipe.timing(key, dt)
        for label in request.labels:
            pipe.incr(key + '.label.%s' % label)
            if dt:
                pipe.timing(key + '.label.%s' % label, dt)
        pipe.incr(key + '.size.%s' % len(request.labels))
        if dt:
            pipe.timing(key + '.size.%s' % len(request.labels), dt)
        pipe.send()

    def emitStatsResources(self):
        if not self.statsd:
            return

        for tenant, resources in self.current_resources_by_tenant.items():
            for resource, value in resources.items():
                key = 'zuul.nodepool.resources.tenant.' \
                      '{tenant}.{resource}'
                self.statsd.gauge(key, value, tenant=tenant, resource=resource)
        for project, resources in self.current_resources_by_project.items():
            for resource, value in resources.items():
                key = 'zuul.nodepool.resources.project.' \
                      '{project}.{resource}'
                self.statsd.gauge(
                    key, value, project=project, resource=resource)

    def emitStatsResourceCounters(self, tenant, project, resources, duration):
        if not self.statsd:
            return

        for resource, value in resources.items():
            key = 'zuul.nodepool.resources.tenant.{tenant}.{resource}'
            self.statsd.incr(
                key, value * duration, tenant=tenant, resource=resource)
        for resource, value in resources.items():
            key = 'zuul.nodepool.resources.project.' \
                  '{project}.{resource}'
            self.statsd.incr(
                key, value * duration, project=project, resource=resource)

    def requestNodes(self, build_set_uuid, job, tenant_name, pipeline_name,
                     provider, priority, relative_priority, event=None):
        log = get_annotated_logger(self.log, event)
        labels = [n.label for n in job.nodeset.getNodes()]
        if event:
            event_id = event.zuul_event_id
        else:
            event_id = None
        req = model.NodeRequest(self.system_id, build_set_uuid, tenant_name,
                                pipeline_name, job.name, labels, provider,
                                relative_priority, event_id)
        self.requests[req.uid] = req

        if job.nodeset.nodes:
            self.zk_nodepool.submitNodeRequest(req, priority)
            # Logged after submission so that we have the request id
            log.info("Submitted node request %s", req)
            self.emitStats(req)
        else:
            # Directly fulfill the node request before submitting it to ZK, so
            # nodepool doesn't have to deal with it.
            req.state = model.STATE_FULFILLED
            self.zk_nodepool.submitNodeRequest(req, priority)
            # Logged after submission so that we have the request id
            log.info("Submitted empty node request %s", req)
        return req

    def cancelRequest(self, request):
        log = get_annotated_logger(self.log, request.event_id)
        log.info("Canceling node request %s", request)
        # TODO (felix): This flag might not be relevant anymore as it's not
        # stored in ZK. Should we just remove the condition and always delete
        # the request?
        if not request.canceled:
            try:
                request.canceled = True
                self.zk_nodepool.deleteNodeRequest(request)
            except Exception:
                log.exception("Error deleting node request:")

        if request.uid in self.requests:
            del self.requests[request.uid]
            self.emitStats(request)

    def reviseRequest(self, request, relative_priority=None):
        '''Attempt to update the node request, if it is not currently being
        processed.

        :param: NodeRequest request: The request to update.
        :param relative_priority int: If supplied, the new relative
            priority to set on the request.

        '''
        log = get_annotated_logger(self.log, request.event_id)
        if relative_priority is None:
            return
        try:
            self.zk_nodepool.lockNodeRequest(request, blocking=False)
        except LockException:
            # It may be locked by nodepool, which is fine.
            log.debug("Unable to revise locked node request %s", request)
            return False
        try:
            old_priority = request.relative_priority
            request.relative_priority = relative_priority
            self.zk_nodepool.storeNodeRequest(request)
            log.debug("Revised relative priority of "
                      "node request %s from %s to %s",
                      request, old_priority, relative_priority)
        except Exception:
            log.exception("Unable to update node request %s", request)
        finally:
            try:
                self.zk_nodepool.unlockNodeRequest(request)
            except Exception:
                log.exception("Unable to unlock node request %s", request)

    # TODO (felix): Switch back to use a build object here rather than the
    # ansible_job once it's available via ZK.
    def holdNodeSet(self, nodeset, request, ansible_job):
        '''
        Perform a hold on the given set of nodes.

        :param NodeSet nodeset: The object containing the set of nodes to hold.
        :param HoldRequest request: Hold request associated with the NodeSet
        '''
        self.log.info("Holding nodeset %s" % (nodeset,))
        resources = defaultdict(int)
        nodes = nodeset.getNodes()

        args = ansible_job.arguments
        project = args["zuul"]["project"]["canonical_name"]
        tenant = args["zuul"]["tenant"]
        duration = 0
        if ansible_job.end_time and ansible_job.time_starting_build:
            duration = ansible_job.end_time - ansible_job.time_starting_build
        self.log.info(
            "Nodeset %s with %s nodes was in use for %s seconds for build %s "
            "for project %s",
            nodeset, len(nodeset.nodes), duration, ansible_job, project)

        for node in nodes:
            if node.lock is None:
                raise Exception("Node %s is not locked" % (node,))
            if node.resources:
                add_resources(resources, node.resources)
            node.state = model.STATE_HOLD
            node.hold_job = " ".join([request.tenant,
                                      request.project,
                                      request.job,
                                      request.ref_filter])
            node.comment = request.reason
            if request.node_expiration:
                node.hold_expiration = request.node_expiration
            self.zk_nodepool.storeNode(node)

        request.nodes.append(dict(
            build=ansible_job.build_request.uuid,
            nodes=[node.id for node in nodes],
        ))
        request.current_count += 1

        # Request has been used at least the maximum number of times so set
        # the expiration time so that it can be auto-deleted.
        if request.current_count >= request.max_count and not request.expired:
            request.expired = time.time()

        # Give ourselves a few seconds to try to obtain the lock rather than
        # immediately give up.
        self.zk_nodepool.lockHoldRequest(request, timeout=5)

        try:
            self.zk_nodepool.storeHoldRequest(request)
        except Exception:
            # If we fail to update the request count, we won't consider it
            # a real autohold error by passing the exception up. It will
            # just get used more than the original count specified.
            # It's possible to leak some held nodes, though, which would
            # require manual node deletes.
            self.log.exception("Unable to update hold request %s:", request)
        finally:
            # Although any exceptions thrown here are handled higher up in
            # _doBuildCompletedEvent, we always want to try to unlock it.
            self.zk_nodepool.unlockHoldRequest(request)

        # When holding a nodeset we need to update the gauges to avoid
        # leaking resources
        if tenant and project and resources:
            subtract_resources(
                self.current_resources_by_tenant[tenant], resources)
            subtract_resources(
                self.current_resources_by_project[project], resources)
            self.emitStatsResources()

            if duration:
                self.emitStatsResourceCounters(
                    tenant, project, resources, duration)

    # TODO (felix): Switch back to use a build object here rather than the
    # ansible_job once it's available via ZK.
    def useNodeSet(self, nodeset, ansible_job=None):
        self.log.info("Setting nodeset %s in use", nodeset)
        resources = defaultdict(int)
        for node in nodeset.getNodes():
            if node.lock is None:
                raise Exception("Node %s is not locked", node)
            node.state = model.STATE_IN_USE
            self.zk_nodepool.storeNode(node)
            if node.resources:
                add_resources(resources, node.resources)
        if ansible_job and resources:
            args = ansible_job.arguments
            # we have a buildset and thus also tenant and project so we
            # can emit project specific resource usage stats
            tenant_name = args["zuul"]["tenant"]
            project_name = args["zuul"]["project"]["canonical_name"]

            self.current_resources_by_tenant.setdefault(
                tenant_name, defaultdict(int))
            self.current_resources_by_project.setdefault(
                project_name, defaultdict(int))

            add_resources(self.current_resources_by_tenant[tenant_name],
                          resources)
            add_resources(self.current_resources_by_project[project_name],
                          resources)
            self.emitStatsResources()

    # TODO (felix): Switch back to use a build object here rather than the
    # ansible_job once it's available via ZK.
    def returnNodeSet(self, nodeset, ansible_job=None, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        log.info("Returning nodeset %s", nodeset)
        resources = defaultdict(int)

        for node in nodeset.getNodes():
            if node.lock is None:
                log.error("Node %s is not locked", node)
            else:
                try:
                    if node.state == model.STATE_IN_USE:
                        if node.resources:
                            add_resources(resources, node.resources)
                        node.state = model.STATE_USED
                        self.zk_nodepool.storeNode(node)
                except Exception:
                    log.exception("Exception storing node %s "
                                  "while unlocking:", node)
        self.unlockNodeSet(nodeset)

        if not ansible_job:
            return

        args = ansible_job.arguments
        project = args["zuul"]["project"]["canonical_name"]
        tenant = args["zuul"]["tenant"]
        duration = 0
        if ansible_job.end_time and ansible_job.time_starting_build:
            duration = ansible_job.end_time - ansible_job.time_starting_build
        log.info("Nodeset %s with %s nodes was in use "
                 "for %s seconds for build %s for project %s",
                 nodeset, len(nodeset.nodes), duration, ansible_job, project)

        # When returning a nodeset we need to update the gauges if we have a
        # build. Further we calculate resource*duration and increment their
        # tenant or project specific counters. With that we have both the
        # current value and also counters to be able to perform accounting.
        if resources:
            subtract_resources(
                self.current_resources_by_tenant[tenant], resources)
            subtract_resources(
                self.current_resources_by_project[project], resources)
            self.emitStatsResources()

            if duration:
                self.emitStatsResourceCounters(
                    tenant, project, resources, duration)

    def unlockNodeSet(self, nodeset):
        self._unlockNodes(nodeset.getNodes())

    def _unlockNodes(self, nodes):
        for node in nodes:
            try:
                self.zk_nodepool.unlockNode(node)
            except Exception:
                self.log.exception("Error unlocking node:")

    def lockNodes(self, request, nodeset):
        # Try to lock all of the supplied nodes.  If any lock fails,
        # try to unlock any which have already been locked before
        # re-raising the error.
        locked_nodes = []
        try:
            for node_id, node in zip(request.nodes, nodeset.getNodes()):
                self.zk_nodepool.updateNode(node, node_id)
                if node.allocated_to != request.id:
                    raise Exception("Node %s allocated to %s, not %s" %
                                    (node.id, node.allocated_to, request.id))
                self.log.debug("Locking node %s" % (node,))
                self.zk_nodepool.lockNode(node, timeout=30)
                # Check the allocated_to again to ensure that nodepool didn't
                # re-allocate the nodes to a different node request while we
                # were locking them.
                if node.allocated_to != request.id:
                    raise Exception(
                        "Node %s was reallocated during locking %s, not %s" %
                        (node.id, node.allocated_to, request.id))
                locked_nodes.append(node)
        except Exception:
            self.log.exception("Error locking nodes:")
            self._unlockNodes(locked_nodes)
            raise

    def checkNodeRequest(self, request, request_id, job_nodeset):
        """
        Called by the scheduler when it wants to accept a node request for
        potential use of its nodes. The nodes itself will be accepted and
        locked by the executor when the corresponding job is started.

        :returns: A new NodeSet object which contains information from
            nodepool about the actual allocated nodes.
        """
        log = get_annotated_logger(self.log, request.event_id)
        log.info("Accepting node request %s", request)
        # A copy of the nodeset with information about the real nodes
        nodeset = job_nodeset.copy()

        if request.canceled:
            log.info("Ignoring canceled node request %s", request)
            # The request was already deleted when it was canceled
            return None

        # If we didn't request nodes and the request is fulfilled then just
        # reutrn. We don't have to do anything in this case. Further don't even
        # ask ZK for the request as empty requests are not put into ZK.
        if not request.labels and request.fulfilled:
            return nodeset

        # Load the node info from ZK.
        try:
            for node_id, node in zip(request.nodes, nodeset.getNodes()):
                self.zk_nodepool.updateNode(node, node_id)
        except Exception:
            # If we cannot retrieve the node request from ZK we
            # probably lost the connection and thus the ZK
            # session. Just log the problem with zookeeper and fail
            # here.
            log.exception("Error getting node request %s:", request_id)
            request.failed = True
            return nodeset

        return nodeset

    def acceptNodes(self, request, nodeset):
        # Accept the nodes supplied by request, mutate nodeset with
        # the real node information.
        locked = False
        if request.fulfilled:
            # If the request succeeded, try to lock the nodes.
            try:
                nodes = self.lockNodes(request, nodeset)
                locked = True
            except Exception:
                log = get_annotated_logger(self.log, request.event_id)
                log.exception("Error locking nodes:")
                request.failed = True

        # Regardless of whether locking (or even the request)
        # succeeded, delete the request.
        self.deleteNodeRequest(request, locked)

        if request.failed:
            raise Exception("Accepting nodes failed")
        return nodes

    def deleteNodeRequest(self, request, locked=False):
        log = get_annotated_logger(self.log, request.event_id)
        log.debug("Deleting node request %s", request)
        try:
            self.zk_nodepool.deleteNodeRequest(request)
        except Exception:
            log.exception("Error deleting node request:")
            request.failed = True
            # If deleting the request failed, and we did lock the
            # nodes, unlock the nodes since we're not going to use
            # them.
            if locked:
                self.unlockNodeSet(request.nodeset)
