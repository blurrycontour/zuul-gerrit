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
import time

from collections import defaultdict
from zuul import model
from zuul.lib.logutil import get_annotated_logger
from zuul.zk.exceptions import LockException
from zuul.zk.nodepool import ZooKeeperNodepool


def add_resources(target, source):
    for key, value in source.items():
        target[key] += value


def subtract_resources(target, source):
    for key, value in source.items():
        target[key] -= value


class Nodepool(object):
    log = logging.getLogger('zuul.nodepool')

    def __init__(self, zk_client, hostname, statsd, scheduler=None):
        self.hostname = hostname
        self.statsd = statsd
        # TODO (felix): Remove the scheduler parameter once the nodes are
        # locked on the executor side.
        self.sched = scheduler

        self.zk_nodepool = ZooKeeperNodepool(zk_client)

        self.requests = {}
        self.current_resources_by_tenant = {}
        self.current_resources_by_project = {}

    def emitStats(self, request):
        # Implements the following :
        #  counter zuul.nodepool.requests.<state>.total
        #  counter zuul.nodepool.requests.<state>.label.<label>
        #  counter zuul.nodepool.requests.<state>.size.<size>
        #  timer   zuul.nodepool.requests.(fulfilled|failed)
        #  timer   zuul.nodepool.requests.(fulfilled|failed).<label>
        #  timer   zuul.nodepool.requests.(fulfilled|failed).<size>
        #  gauge   zuul.nodepool.current_requests
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
        for node in request.nodeset.getNodes():
            pipe.incr(key + '.label.%s' % node.label)
            if dt:
                pipe.timing(key + '.label.%s' % node.label, dt)
        pipe.incr(key + '.size.%s' % len(request.nodeset.nodes))
        if dt:
            pipe.timing(key + '.size.%s' % len(request.nodeset.nodes), dt)
        pipe.gauge('zuul.nodepool.current_requests', len(self.requests))
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
        # Create a copy of the nodeset to represent the actual nodes
        # returned by nodepool.
        nodeset = job.nodeset.copy()
        if event:
            event_id = event.zuul_event_id
        else:
            event_id = None
        req = model.NodeRequest(self.hostname, build_set_uuid, tenant_name,
                                pipeline_name, job.name, nodeset, provider,
                                relative_priority, event_id)
        self.requests[req.uid] = req

        if nodeset.nodes:
            self.zk_nodepool.submitNodeRequest(
                req, priority, self._updateNodeRequest)
            # Logged after submission so that we have the request id
            log.info("Submitted node request %s", req)
            self.emitStats(req)
        else:
            log.info("Fulfilling empty node request %s", req)
            req.state = model.STATE_FULFILLED
            if self.sched is not None:
                # TODO (felix): Remove this call once the nodes are locked on
                # the executor side.
                self.sched.onNodesProvisioned(req)
            del self.requests[req.uid]
        return req

    def cancelRequest(self, request):
        log = get_annotated_logger(self.log, request.event_id)
        log.info("Canceling node request %s", request)
        if not request.canceled:
            try:
                request.canceled = True
                self.zk_nodepool.deleteNodeRequest(request)
            except Exception:
                log.exception("Error deleting node request:")

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
        self._unlockNodes(nodeset.getNodes())

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

    def lockNodeSet(self, nodeset, request_id):
        # Try to lock all of the supplied nodes.  If any lock fails,
        # try to unlock any which have already been locked before
        # re-raising the error.
        locked_nodes = []
        try:
            for node in nodeset.getNodes():
                if node.allocated_to != request_id:
                    raise Exception("Node %s allocated to %s, not %s" %
                                    (node.id, node.allocated_to, request_id))
                self.log.debug("Locking node %s" % (node,))
                self.zk_nodepool.lockNode(node, timeout=30)
                # Check the allocated_to again to ensure that nodepool didn't
                # re-allocate the nodes to a different node request while we
                # were locking them.
                if node.allocated_to != request_id:
                    raise Exception(
                        "Node %s was reallocated during locking %s, not %s" %
                        (node.id, node.allocated_to, request_id))
                locked_nodes.append(node)
        except Exception:
            self.log.exception("Error locking nodes:")
            self._unlockNodes(locked_nodes)
            raise

    def _updateNodeRequest(self, request, priority, deleted):
        log = get_annotated_logger(self.log, request.event_id)
        # Return False to indicate that we should stop watching the
        # node.
        log.debug("Updating node request %s", request)

        if request.uid not in self.requests:
            log.debug("Request %s is unknown", request)
            return False

        if request.canceled:
            log.debug("Node request %s was canceled", request)
            del self.requests[request.uid]
            self.emitStats(request)
            return False

        # TODOv3(jeblair): handle allocation failure
        if deleted:
            log.debug("Resubmitting lost node request %s", request)
            request.reset()
            self.zk_nodepool.submitNodeRequest(
                request, priority, self._updateNodeRequest)
            # Stop watching this request node
            return False
        elif request.state in (model.STATE_FULFILLED, model.STATE_FAILED):
            log.info("Node request %s %s", request, request.state)

            # Give our results to the scheduler.
            if self.sched is not None:
                # TODO (felix): Remove this call once the nodes are locked on
                # the executor side.
                self.sched.onNodesProvisioned(request)
            del self.requests[request.uid]

            self.emitStats(request)

            # Stop watching this request node.
            return False

        return True

    def checkNodeRequest(self, request, request_id):
        """
        Called by the scheduler when it wants to accept a node request for
        potential use of its nodes. The nodes itself will be accepted and
        locked by the executor when the corresponding job is started.

        :returns: False if there is a problem with the request (canceled or
            retrying), True if it is ready to be acted upon (success or
            failure).
        """
        log = get_annotated_logger(self.log, request.event_id)
        log.info("Accepting node request %s", request)

        if request_id != request.id:
            log.info("Skipping node accept for %s (resubmitted as %s)",
                     request_id, request.id)
            return False

        if request.canceled:
            log.info("Ignoring canceled node request %s", request)
            # The request was already deleted when it was canceled
            return False

        # If we didn't request nodes and the request is fulfilled then just
        # reutrn. We don't have to do anything in this case. Further don't even
        # ask ZK for the request as empty requests are not put into ZK.
        if not request.nodeset.nodes and request.fulfilled:
            return True

        # Make sure the request still exists. It's possible it could have
        # disappeared if we lost the ZK session between when the fulfillment
        # response was added to our queue, and when we actually get around to
        # processing it. Nodepool will automatically reallocate the assigned
        # nodes in that situation.
        try:
            if not self.zk_nodepool.nodeRequestExists(request):
                log.info("Request %s no longer exists, resubmitting",
                         request.id)
                # Look up the priority from the old request id.
                priority = request.id.partition("-")[0]
                self.requests[request.uid] = request
                request.reset()
                self.zk_nodepool.submitNodeRequest(
                    request, priority, self._updateNodeRequest)
                return False
        except Exception:
            # If we cannot retrieve the node request from ZK we probably lost
            # the connection and thus the ZK session. Resubmitting the node
            # request probably doesn't make sense at this point in time as it
            # is likely to directly fail again. So just log the problem
            # with zookeeper and fail here.
            log.exception("Error getting node request %s:", request_id)
            request.failed = True
            return True

        return True

    def acceptNodes(self, request):
        locked = False
        if request.fulfilled:
            # If the request succeeded, try to lock the nodes.
            try:
                self.lockNodeSet(request.nodeset, request.id)
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
