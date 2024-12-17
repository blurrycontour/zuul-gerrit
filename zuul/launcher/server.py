# Copyright 2024 BMW Group
# Copyright 2024 Acme Gating, LLC
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

from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import collections
import itertools
import logging
import os
import random
import socket
import subprocess
import threading
import time
import uuid

import mmh3
import requests

from zuul import model
from zuul.lib import commandsocket, tracing
from zuul.lib.collections import DefaultKeyDict
from zuul.lib.config import get_default
from zuul.zk.image_registry import (
    ImageBuildRegistry,
    ImageUploadRegistry,
)
from zuul.lib.logutil import get_annotated_logger
from zuul.version import get_version_string
from zuul.zk import ZooKeeperClient
from zuul.zk.components import COMPONENT_REGISTRY, LauncherComponent
from zuul.zk.exceptions import LockException
from zuul.zk.event_queues import (
    PipelineResultEventQueue,
    TenantTriggerEventQueue,
)
from zuul.zk.launcher import LauncherApi
from zuul.zk.layout import (
    LayoutProvidersStore,
    LayoutStateStore,
)
from zuul.zk.locks import tenant_read_lock
from zuul.zk.system import ZuulSystem
from zuul.zk.zkobject import ZKContext

COMMANDS = (
    commandsocket.StopCommand,
)

# What gets written to disk in a single write() call; should be a
# multiple of 4k block size.
DOWNLOAD_BLOCK_SIZE = 1024 * 64
# The byte range size for an individual GET operation.  Should be a
# multiple of the above.  Current value is approx 100MiB.
DOWNLOAD_CHUNK_SIZE = DOWNLOAD_BLOCK_SIZE * 1525


def scores_for_label(label_cname, candidate_names):
    return {
        mmh3.hash(f"{n}-{label_cname}", signed=False): n
        for n in candidate_names
    }


class NodesetRequestError(Exception):
    """Errors that should lead to the request being declined."""
    pass


class ProviderNodeError(Exception):
    """Errors that should lead to the provider node being failed."""
    pass


class DeleteJob:
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, launcher, image_build_artifact, upload):
        self.launcher = launcher
        self.image_build_artifact = image_build_artifact
        self.upload = upload

    def run(self):
        try:
            self._run()
        except Exception:
            self.log.exception("Error in delete job")

    def _run(self):
        try:
            with self.launcher.createZKContext(None, self.log) as ctx:
                try:
                    with self.upload.locked(ctx, blocking=False):
                        self.log.info("Deleting image upload %s", self.upload)
                        with self.upload.activeContext(ctx):
                            self.upload.state = model.STATE_DELETING
                        provider_cname = self.upload.providers[0]
                        provider = self.launcher.\
                            _getProviderByCanonicalName(provider_cname)
                        provider.deleteImage(self.upload.external_id)
                        self.upload.delete(ctx)
                        self.launcher.upload_deleted_event.set()
                        self.launcher.wake_event.set()
                except LockException:
                    return
        except Exception:
            self.log.exception("Unable to delete upload %s", self.upload)


class UploadJob:
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, launcher, image_build_artifact, uploads):
        self.launcher = launcher
        self.image_build_artifact = image_build_artifact
        self.uploads = uploads

    def run(self):
        try:
            self._run()
        except Exception:
            self.log.exception("Error in upload job")

    def _run(self):
        # TODO: check if endpoint can handle direct import from URL,
        # and skip download
        acquired = []
        path = None
        with self.launcher.createZKContext(None, self.log) as ctx:
            try:
                try:
                    with self.image_build_artifact.locked(ctx, blocking=False):
                        for upload in self.uploads:
                            if upload.acquireLock(ctx, blocking=False):
                                acquired.append(upload)
                                self.log.debug("Acquired upload lock for %s",
                                               upload)
                                with upload.activeContext(ctx):
                                    upload.state = model.STATE_UPLOADING
                except LockException:
                    # We may have raced the unlock of the iba after
                    # the upload was created; set the event to try
                    # again.
                    self.launcher.upload_added_event.set()
                    return

                if not acquired:
                    return

                path = self.launcher.downloadArtifact(
                    self.image_build_artifact)
                futures = []
                for upload in acquired:
                    future = self.launcher.endpoint_upload_executor.submit(
                        EndpointUploadJob(
                            self.launcher, self.image_build_artifact,
                            upload, path).run)
                    futures.append((upload, future))
                for upload, future in futures:
                    try:
                        future.result()
                        self.log.info("Finished upload %s", upload)
                    except Exception:
                        self.log.exception("Unable to upload image %s", upload)
            finally:
                for upload in acquired:
                    try:
                        upload.releaseLock(ctx)
                        self.log.debug("Released upload lock for %s", upload)
                    except Exception:
                        self.log.exception("Unable to release lock for %s",
                                           upload)
                    try:
                        with upload.activeContext(ctx):
                            if upload.external_id:
                                upload.state = model.STATE_READY
                            else:
                                upload.state = model.STATE_PENDING
                    except Exception:
                        self.log.exception("Unable to update state for %s",
                                           upload)
                if path:
                    try:
                        os.unlink(path)
                        self.log.info("Deleted %s", path)
                    except Exception:
                        self.log.exception("Unable to delete %s", path)


class EndpointUploadJob:
    log = logging.getLogger("zuul.Launcher")

    def __init__(self, launcher, artifact, upload, path):
        self.launcher = launcher
        self.artifact = artifact
        self.upload = upload
        self.path = path

    def run(self):
        try:
            self._run()
        except Exception:
            self.log.exception("Error in endpoint upload job")

    def _run(self):
        # The upload has a list of providers with identical
        # configurations.  Pick one of them as a representative.
        self.log.info("Starting upload %s", self.upload)
        provider_cname = self.upload.providers[0]
        provider = self.launcher._getProviderByCanonicalName(provider_cname)
        provider_image = None
        for image in provider.images.values():
            if image.canonical_name == self.upload.canonical_name:
                provider_image = image
        if provider_image is None:
            raise Exception(
                f"Unable to find image {self.upload.canonical_name}")

        # TODO: add upload id, etc
        metadata = {}
        image_name = f'{provider_image.name}-{self.artifact.uuid}'
        external_id = provider.uploadImage(
            provider_image, image_name, self.path, self.artifact.format,
            metadata, self.artifact.md5sum, self.artifact.sha256)
        with self.launcher.createZKContext(self.upload._lock, self.log) as ctx:
            self.upload.updateAttributes(
                ctx,
                external_id=external_id,
                timestamp=time.time())
        if not self.upload.validated:
            self.launcher.addImageValidateEvent(self.upload)


class Launcher:
    log = logging.getLogger("zuul.Launcher")
    # Max. time to wait for a cache to sync
    CACHE_SYNC_TIMEOUT = 10
    # Max. time the main event loop is allowed to sleep
    MAX_SLEEP = 1
    DELETE_TIMEOUT = 600

    def __init__(self, config, connections):
        self._running = True
        self.config = config
        self.connections = connections
        # All tenants and all providers
        self.tenant_providers = {}
        # Only endpoints corresponding to connections handled by this
        # launcher
        self.endpoints = {}

        self.tracing = tracing.Tracing(self.config)
        self.zk_client = ZooKeeperClient.fromConfig(self.config)
        self.zk_client.connect()

        self.system = ZuulSystem(self.zk_client)
        self.trigger_events = TenantTriggerEventQueue.createRegistry(
            self.zk_client, self.connections
        )
        self.result_events = PipelineResultEventQueue.createRegistry(
            self.zk_client
        )

        COMPONENT_REGISTRY.create(self.zk_client)
        self.hostname = get_default(self.config, "launcher", "hostname",
                                    socket.getfqdn())
        self.component_info = LauncherComponent(
            self.zk_client, self.hostname, version=get_version_string())
        self.component_info.register()
        self.wake_event = threading.Event()
        self.stop_event = threading.Event()

        self.connection_filter = get_default(
            self.config, "launcher", "connection_filter")
        self.api = LauncherApi(
            self.zk_client, COMPONENT_REGISTRY.registry, self.component_info,
            self.wake_event.set, self.connection_filter)

        self.temp_dir = get_default(self.config, 'launcher', 'temp_dir',
                                    '/tmp', expand_user=True)

        self.command_map = {
            commandsocket.StopCommand.name: self.stop,
        }
        command_socket = get_default(
            self.config, "launcher", "command_socket",
            "/var/lib/zuul/launcher.socket")
        self.command_socket = commandsocket.CommandSocket(command_socket)
        self._command_running = False

        self.layout_updated_event = threading.Event()
        self.layout_updated_event.set()

        self.upload_added_event = threading.Event()
        self.upload_deleted_event = threading.Event()

        self.tenant_layout_state = LayoutStateStore(
            self.zk_client, self._layoutUpdatedCallback)
        self.layout_providers_store = LayoutProvidersStore(
            self.zk_client, self.connections)
        self.local_layout_state = {}

        self.image_build_registry = ImageBuildRegistry(self.zk_client)
        self.image_upload_registry = ImageUploadRegistry(
            self.zk_client,
            self._uploadAddedCallback
        )

        self.launcher_thread = threading.Thread(
            target=self.run,
            name="Launcher",
        )
        # Simultaneous image artifact processes (download+upload)
        self.upload_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="UploadWorker",
        )
        # Simultaneous uploads
        self.endpoint_upload_executor = ThreadPoolExecutor(
            # TODO: make configurable
            max_workers=10,
            thread_name_prefix="UploadWorker",
        )

    def _layoutUpdatedCallback(self):
        self.layout_updated_event.set()
        self.wake_event.set()

    def _uploadAddedCallback(self):
        self.upload_added_event.set()
        self.wake_event.set()

    def run(self):
        self.component_info.state = self.component_info.RUNNING
        self.log.debug("Launcher running")
        while self._running:
            loop_start = time.monotonic()
            try:
                self._run()
            except Exception:
                self.log.exception("Error in main thread:")
            loop_duration = time.monotonic() - loop_start
            time.sleep(max(0, self.MAX_SLEEP - loop_duration))
            self.wake_event.wait()
            self.wake_event.clear()

    def _run(self):
        if self.layout_updated_event.is_set():
            self.layout_updated_event.clear()
            if self.updateTenantProviders():
                self.checkOldImages()
                self.checkMissingImages()
                self.checkMissingUploads()
        if self.upload_added_event.is_set():
            self.checkOldImages()
            self.checkMissingUploads()
        if self.upload_deleted_event.is_set():
            self.checkOldImages()
        self._processRequests()
        self._processNodes()
        self._processMinReady()

    def _processRequests(self):
        ready_nodes = self._getUnassignedReadyNodes()
        for request in self.api.getMatchingRequests():
            log = get_annotated_logger(self.log, request, request=request.uuid)
            if not request.hasLock():
                if request.state in request.FINAL_STATES:
                    # Nothing to do here
                    continue
                log.debug("Got request %s", request)
                with self.createZKContext(None, log) as ctx:
                    if not request.acquireLock(ctx, blocking=False):
                        log.debug("Failed to lock matching request %s",
                                  request)
                        continue

            if not self._cachesReadyForRequest(request):
                self.log.debug("Caches are not up-to-date for %s", request)
                continue

            try:
                if request.state == model.NodesetRequest.State.REQUESTED:
                    self._acceptRequest(request, log, ready_nodes)
                elif request.state == model.NodesetRequest.State.ACCEPTED:
                    self._checkRequest(request, log)
            except NodesetRequestError as err:
                state = model.NodesetRequest.State.FAILED
                log.error("Marking request %s as %s: %s",
                          request, state, str(err))
                event = model.NodesProvisionedEvent(
                    request.uuid, request.buildset_uuid)
                self.result_events[request.tenant_name][
                    request.pipeline_name].put(event)
                with self.createZKContext(request._lock, log) as ctx:
                    request.updateAttributes(ctx, state=state)
            except Exception:
                log.exception("Error processing request %s", request)
            if request.state in request.FINAL_STATES:
                with self.createZKContext(None, log) as ctx:
                    request.releaseLock(ctx)

    def _cachesReadyForRequest(self, request):
        # Make sure we have all associated provider nodes in the cache
        return all(
            self.api.getProviderNode(n)
            for n in itertools.chain.from_iterable(request.provider_nodes)
        )

    def _acceptRequest(self, request, log, ready_nodes):
        log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        provider_nodes = []
        label_providers = self._selectProviders(request, log)
        with self.createZKContext(request._lock, log) as ctx:
            for i, (label, provider) in enumerate(label_providers):
                # TODO: sort by age? use old nodes first? random to reduce
                # chance of thundering herd?
                for node in list(ready_nodes.get(label.name, [])):
                    if node.is_locked:
                        continue
                    if node.hasExpired():
                        continue
                    for provider in self.tenant_providers[request.tenant_name]:
                        if provider.connection_name != node.connection_name:
                            continue
                        if not (plabel := provider.labels.get(label.name)):
                            continue
                        if node.label_config_hash != plabel.config_hash:
                            continue
                        break
                    else:
                        continue

                    if not node.acquireLock(ctx, blocking=False):
                        log.debug("Failed to lock matching ready node %s",
                                  node)
                        continue
                    try:
                        tags = provider.getNodeTags(
                            self.system.system_id, label, node.uuid,
                            provider, request)
                        with self.createZKContext(node._lock, self.log) as ctx:
                            node.updateAttributes(
                                ctx,
                                request_id=request.uuid,
                                tenant_name=request.tenant_name,
                                tags=tags,
                            )
                        ready_nodes[label.name].remove(node)
                        log.debug("Assigned ready node %s", node.uuid)
                        break
                    except Exception:
                        log.exception("Faild to assign ready node %s", node)
                        continue
                    finally:
                        node.releaseLock(ctx)
                else:
                    node = self._requestNode(
                        label, request, provider, log, ctx)
                    log.debug("Requested node %s", node.uuid)
                provider_nodes.append([node.uuid])

            request.updateAttributes(
                ctx,
                state=model.NodesetRequest.State.ACCEPTED,
                provider_nodes=provider_nodes)

    def _selectProviders(self, request, log):
        providers = self.tenant_providers.get(request.tenant_name)
        if not providers:
            raise NodesetRequestError(
                f"No provider for tenant {request.tenant_name}")

        existing_nodes = [
            self.api.getProviderNode(n)
            for n in itertools.chain.from_iterable(request.provider_nodes)
        ]
        provider_failures = collections.Counter(
            n.provider for n in existing_nodes
            if n.state == n.State.FAILED)

        label_providers = []
        for i, label_name in enumerate(request.labels):
            candidate_providers = [
                p for p in providers
                if p.hasLabel(label_name)
                and provider_failures[p.canonical_name] < p.launch_attempts
            ]
            if not candidate_providers:
                raise NodesetRequestError(
                    f"No provider found for label {label_name}")

            log.debug("Candidate providers: %s", candidate_providers)
            # TODO: make provider selection more sophisticated
            provider = random.choice(candidate_providers)
            label = provider.labels[label_name]
            label_providers.append((label, provider))
        return label_providers

    def _requestNode(self, label, request, provider, log, ctx):
        # Create a deterministic node UUID by using
        # the request UUID as namespace.
        node_uuid = uuid.uuid4().hex
        image = provider.images[label.image]
        tags = provider.getNodeTags(
            self.system.system_id, label, node_uuid, provider, request)
        node_class = provider.driver.getProviderNodeClass()
        node = node_class.new(
            ctx,
            uuid=node_uuid,
            label=label.name,
            label_config_hash=label.config_hash,
            max_ready_age=label.max_ready_age,
            request_id=request.uuid,
            zuul_event_id=request.zuul_event_id,
            connection_name=provider.connection_name,
            tenant_name=request.tenant_name,
            provider=provider.canonical_name,
            tags=tags,
            # Set any node attributes we already know here
            connection_port=image.connection_port,
            connection_type=image.connection_type,
        )
        log.debug("Requested node %s", node)
        return node

    def _checkRequest(self, request, log):
        log.debug("Checking request %s", request)
        requested_nodes = [self.api.getProviderNode(p)
                           for p in request.nodes]

        requested_nodes = []
        for i, node_id in enumerate(request.nodes):
            node = self.api.getProviderNode(node_id)
            if node.state == node.State.FAILED:
                label_providers = self._selectProviders(request, log)
                label, provider = label_providers[i]
                log.info("Retrying request with provider %s", provider)
                with self.createZKContext(request._lock, log) as ctx:
                    node = self._requestNode(
                        label, request, provider, log, ctx)
                    with request.activeContext(ctx):
                        request.provider_nodes[i].append(node.uuid)

            requested_nodes.append(node)

        if not all(n.state in n.FINAL_STATES for n in requested_nodes):
            return
        log.debug("Request %s nodes ready: %s", request, requested_nodes)
        failed = not all(n.state in model.ProviderNode.State.READY
                         for n in requested_nodes)
        # TODO:
        # * gracefully handle node failures (retry with another connection)
        # * deallocate ready nodes from the request if finally failed

        state = (model.NodesetRequest.State.FAILED if failed
                 else model.NodesetRequest.State.FULFILLED)
        log.debug("Marking request %s as %s", request, state)

        event = model.NodesProvisionedEvent(
            request.uuid, request.buildset_uuid)
        self.result_events[request.tenant_name][request.pipeline_name].put(
            event)

        with self.createZKContext(request._lock, log) as ctx:
            request.updateAttributes(ctx, state=state)

    def _processNodes(self):
        for node in self.api.getMatchingProviderNodes():
            log = get_annotated_logger(self.log, node, request=node.request_id)
            if not node.hasLock():
                if not self._isNodeActionable(node):
                    continue

                with self.createZKContext(None, log) as ctx:
                    if not node.acquireLock(ctx, blocking=False):
                        log.debug("Failed to lock matching node %s", node)
                        continue

            request = self.api.getNodesetRequest(node.request_id)
            if ((request or node.request_id is None)
                    and node.state in node.CREATE_STATES):
                try:
                    self._checkNode(node, log)
                except Exception:
                    state = node.State.FAILED
                    log.exception("Marking node %s as %s", node, state)
                    with self.createZKContext(node._lock, self.log) as ctx:
                        with node.activeContext(ctx):
                            node.setState(state)
                        self.wake_event.set()

            # Deallocate ready node w/o a request for re-use
            if (node.request_id and not request
                    and node.state == node.State.READY):
                log.debug("Deallocating ready node %s from missing request %s",
                          node, node.request_id)
                with self.createZKContext(node._lock, self.log) as ctx:
                    node.updateAttributes(
                        ctx,
                        request_id=None,
                        tenant_name=None,
                        provider=None)

            # Mark outdated nodes w/o a request for cleanup when ...
            if not request and (
                    # ... it expired
                    node.hasExpired() or
                    # ... we are sure that our providers are up-to-date
                    # and we can't find a provider for this node.
                    (not self.layout_updated_event.is_set()
                     and not self._hasProvider(node))):
                state = node.State.OUTDATED
                log.debug("Marking node %s as %s", node, state)
                with self.createZKContext(node._lock, self.log) as ctx:
                    with node.activeContext(ctx):
                        node.setState(state)

            # Clean up the node if ...
            if (
                # ... it is associated with a request that no
                # longer exists
                (node.request_id is not None and not request)
                # ... it is failed/outdated
                or node.state in (node.State.FAILED, node.State.OUTDATED)
            ):
                try:
                    self._cleanupNode(node, log)
                except Exception:
                    log.exception("Error in node cleanup")
                    self.wake_event.set()

            if node.state == model.ProviderNode.State.READY:
                with self.createZKContext(None, self.log) as ctx:
                    node.releaseLock(ctx)

    def _isNodeActionable(self, node):
        if node.is_locked:
            return False

        if node.state in node.LAUNCHER_STATES:
            return True

        if node.request_id:
            request_exists = bool(self.api.getNodesetRequest(node.request_id))
            return not request_exists
        elif node.hasExpired():
            return True
        elif not self._hasProvider(node):
            if self.layout_updated_event.is_set():
                # If our providers are not up-to-date we can't be sure
                # there is no provider for this node.
                return False
            # We no longer have a provider that uses the given node
            return True

        return False

    def _checkNode(self, node, log):
        # TODO: check timeout
        with self.createZKContext(node._lock, self.log) as ctx:
            with node.activeContext(ctx):
                if not node.create_state_machine:
                    log.debug("Building node %s", node)
                    provider = self._getProviderForNode(node)
                    image_external_id = self.getImageExternalId(node, provider)
                    log.debug("Node %s external id %s",
                              node, image_external_id)
                    node.create_state_machine = provider.getCreateStateMachine(
                        node, image_external_id, log)

                old_state = node.create_state_machine.state
                log.debug("Checking node %s", node)
                instance = node.create_state_machine.advance()
                new_state = node.create_state_machine.state
                if old_state != new_state:
                    log.debug("Node %s advanced from %s to %s",
                              node, old_state, new_state)
                if not node.create_state_machine.complete:
                    self.wake_event.set()
                    return
                self._updateNodeFromInstance(node, instance)
                node.setState(node.State.READY)
                self.wake_event.set()
                log.debug("Marking node %s as %s", node, node.state)
            node.releaseLock(ctx)

    def _cleanupNode(self, node, log):
        with self.createZKContext(node._lock, self.log) as ctx:
            with node.activeContext(ctx):
                if not node.delete_state_machine:
                    log.debug("Cleaning up node %s", node)
                    provider = self._getProviderForNode(
                        node, ignore_label=True)
                    node.delete_state_machine = provider.getDeleteStateMachine(
                        node, log)

                old_state = node.delete_state_machine.state
                log.debug("Checking node %s cleanup", node)

                now = time.time()
                if (now - node.delete_state_machine.start_time >
                    self.DELETE_TIMEOUT):
                    log.error("Timeout deleting node %s", node)
                    node.delete_state_machine.state =\
                        node.delete_state_machine.COMPLETE
                    node.delete_state_machine.complete = True

                if not node.delete_state_machine.complete:
                    node.delete_state_machine.advance()
                    new_state = node.delete_state_machine.state
                    if old_state != new_state:
                        log.debug("Node %s advanced from %s to %s",
                                  node, old_state, new_state)

            if not node.delete_state_machine.complete:
                self.wake_event.set()
                return

            if not self.api.getNodesetRequest(node.request_id):
                log.debug("Removing provider node %s", node)
                node.delete(ctx)
                node.releaseLock(ctx)

    def _processMinReady(self):
        if not self.api.nodes_cache.waitForSync(
                timeout=self.CACHE_SYNC_TIMEOUT):
            self.log.warning("Timeout waiting %ss for node cache to sync",
                             self.CACHE_SYNC_TIMEOUT)
            return

        for label, provider in self._getMissingMinReadySlots():
            node_uuid = uuid.uuid4().hex
            # We don't pass a provider here as the node should not
            # be directly associated with a tenant or provider.
            tags = provider.getNodeTags(
                self.system.system_id, label, node_uuid)
            node_class = provider.driver.getProviderNodeClass()
            with self.createZKContext(None, self.log) as ctx:
                node = node_class.new(
                    ctx,
                    uuid=node_uuid,
                    label=label.name,
                    label_config_hash=label.config_hash,
                    max_ready_age=label.max_ready_age,
                    request_id=None,
                    connection_name=provider.connection_name,
                    zuul_event_id=uuid.uuid4().hex,
                    tenant_name=None,
                    provider=None,
                    tags=tags,
                )
                self.log.debug("Created min-ready node %s via provider %s",
                               node, provider)

    def _getMissingMinReadySlots(self):
        candidate_launchers = {
            c.hostname: c for c in COMPONENT_REGISTRY.registry.all("launcher")}
        candidate_names = set(candidate_launchers.keys())
        label_scores = DefaultKeyDict(
            lambda lcn: scores_for_label(lcn, candidate_names))

        # Collect min-ready labels that we need to process
        tenant_labels = collections.defaultdict(
            lambda: collections.defaultdict(list))
        for tenant_name, tenant_providers in self.tenant_providers.items():
            for tenant_provider in tenant_providers:
                for label in tenant_provider.labels.values():
                    if not label.min_ready:
                        continue
                    # Check if this launcher is responsible for
                    # spawning min-ready nodes for this label.
                    if not self._hasHighestMinReadyScore(
                            label.canonical_name,
                            label_scores,
                            candidate_launchers):
                        continue
                    # We collect all label variants to determin if
                    # min-ready is satisfied based on the config hashes
                    tenant_labels[tenant_name][label.name].append(label)

        unassigned_hashes = self._getUnassignedNodeLabelHashes()
        for tenant_name, min_ready_labels in tenant_labels.items():
            for label_name, labels in min_ready_labels.items():
                valid_label_hashes = set(lbl.config_hash for lbl in labels)
                tenant_min_ready = sum(
                    1 for h in unassigned_hashes[label_name]
                    if h in valid_label_hashes
                )
                label_providers = [
                    p for p in self.tenant_providers[tenant_name]
                    if p.hasLabel(label_name)
                ]
                for _ in range(tenant_min_ready, labels[0].min_ready):
                    provider = random.choice(label_providers)
                    label = provider.labels[label_name]
                    yield label, provider
                    unassigned_hashes[label.name].append(label.config_hash)

    def _hasHighestMinReadyScore(
            self, label_cname, label_scores, candidate_launchers):
        scores = sorted(label_scores[label_cname].items())
        for score, launcher_name in scores:
            launcher = candidate_launchers.get(launcher_name)
            if not launcher:
                continue
            if launcher.state != launcher.RUNNING:
                continue
            if (launcher.hostname
                    == self.component_info.hostname):
                return True
            return False
        return False

    def _getUnassignedNodeLabelHashes(self):
        ready_nodes = collections.defaultdict(list)
        for node in self.api.getProviderNodes():
            if node.request_id is not None:
                continue
            ready_nodes[node.label].append(node.label_config_hash)
        return ready_nodes

    def _getUnassignedReadyNodes(self):
        ready_nodes = collections.defaultdict(list)
        for node in self.api.getProviderNodes():
            if node.request_id is not None:
                continue
            if node.is_locked or node.state != node.State.READY:
                continue
            ready_nodes[node.label].append(node)
        return ready_nodes

    def _getProviderForNode(self, node, ignore_label=False):
        for tenant_name, tenant_providers in self.tenant_providers.items():
            # Min-ready nodes don't have an assigned tenant
            if node.tenant_name and tenant_name != node.tenant_name:
                continue
            for provider in tenant_providers:
                # Common case when a node is assigned to a provider
                if provider.canonical_name == node.provider:
                    return provider
                # Fallback for min-ready nodes w/o a assigned provider
                if provider.connection_name != node.connection_name:
                    continue
                if ignore_label:
                    return provider
                if not (label := provider.labels.get(node.label)):
                    continue
                if label.config_hash == node.label_config_hash:
                    return provider
        raise ProviderNodeError(f"Unable to find provider for node {node}")

    def _updateNodeFromInstance(self, node, instance):
        if instance is None:
            return

        # TODO:
        # if (pool.use_internal_ip and
        #     (instance.private_ipv4 or instance.private_ipv6)):
        #     server_ip = instance.private_ipv4 or instance.private_ipv6
        # else:
        server_ip = instance.interface_ip

        node.interface_ip = server_ip
        node.public_ipv4 = instance.public_ipv4
        node.private_ipv4 = instance.private_ipv4
        node.public_ipv6 = instance.public_ipv6
        node.private_ipv6 = instance.private_ipv6
        node.host_id = instance.host_id
        node.cloud = instance.cloud
        node.region = instance.region
        node.az = instance.az
        node.driver_data = instance.driver_data
        node.slot = instance.slot

        # If we did not know the resource information before
        # launching, update it now.
        # TODO:
        # node.resources = instance.getQuotaInformation().get_resources()

        # Optionally, if the node has updated values that we set from
        # the image attributes earlier, set those.
        for attr in ('username', 'python_path', 'shell_type',
                     'connection_port', 'connection_type',
                     'host_keys'):
            if hasattr(instance, attr):
                setattr(node, attr, getattr(instance, attr))

        # As a special case for metastatic, if we got node_attributes
        # from the backing driver, use them as default values and let
        # the values from the pool override.
        instance_node_attrs = getattr(instance, 'node_attributes', None)
        if instance_node_attrs is not None:
            attrs = instance_node_attrs.copy()
            if node.attributes:
                attrs.update(node.attributes)
            node.attributes = attrs

    def _getProvider(self, tenant_name, provider_name):
        for provider in self.tenant_providers[tenant_name]:
            if provider.name == provider_name:
                return provider
        raise ProviderNodeError(
            f"Unable to find {provider_name} in tenant {tenant_name}")

    def _hasProvider(self, node):
        try:
            self._getProviderForNode(node)
        except ProviderNodeError:
            return False
        return True

    def _getProviderByCanonicalName(self, provider_cname):
        for tenant_providers in self.tenant_providers.values():
            for provider in tenant_providers:
                if provider.canonical_name == provider_cname:
                    return provider
        raise Exception(f"Unable to find {provider_cname}")

    def start(self):
        self.log.debug("Starting command processor")
        self._command_running = True
        self.command_socket.start()
        self.command_thread = threading.Thread(
            target=self.runCommand, name="command")
        self.command_thread.daemon = True
        self.command_thread.start()

        self.log.debug("Starting launcher thread")
        self.launcher_thread.start()

    def stop(self):
        self.log.debug("Stopping launcher")
        self._running = False
        self.wake_event.set()
        self.component_info.state = self.component_info.STOPPED
        self._command_running = False
        self.command_socket.stop()
        self.connections.stop()
        self.upload_executor.shutdown()
        self.endpoint_upload_executor.shutdown()
        # Endpoints are stopped by drivers
        self.log.debug("Stopped launcher")

    def join(self):
        self.log.debug("Joining launcher")
        self.launcher_thread.join()
        # Don't set the stop event until after the main thread is
        # joined because doing so will terminate the ZKContext.
        self.stop_event.set()
        self.api.stop()
        self.zk_client.disconnect()
        self.tracing.stop()
        self.log.debug("Joined launcher")

    def runCommand(self):
        while self._command_running:
            try:
                command, args = self.command_socket.get()
                if command != '_stop':
                    self.command_map[command](*args)
            except Exception:
                self.log.exception("Exception while processing command")

    def createZKContext(self, lock, log):
        return ZKContext(self.zk_client, lock, self.stop_event, log)

    def updateTenantProviders(self):
        # We need to handle new and deleted tenants, so we need to
        # process all tenants currently known and the new ones.
        tenant_names = set(self.tenant_providers.keys())
        tenant_names.update(self.tenant_layout_state)

        endpoints = {}
        updated = False
        for tenant_name in tenant_names:
            # Reload the tenant if the layout changed.
            if self._updateTenantProviders(tenant_name):
                updated = True

        if updated:
            for providers in self.tenant_providers.values():
                for provider in providers:
                    if (self.connection_filter and
                        provider.connection_name not in
                        self.connection_filter):
                        continue
                    endpoint = provider.getEndpoint()
                    endpoints[endpoint.canonical_name] = endpoint
                    endpoint.start()
            self.endpoints = endpoints
        return updated

    def _updateTenantProviders(self, tenant_name):
        # Reload the tenant if the layout changed.
        updated = False
        if (self.local_layout_state.get(tenant_name)
                == self.tenant_layout_state.get(tenant_name)):
            return updated
        self.log.debug("Updating tenant %s", tenant_name)
        with tenant_read_lock(self.zk_client, tenant_name, self.log) as tlock:
            layout_state = self.tenant_layout_state.get(tenant_name)

            if layout_state:
                with self.createZKContext(tlock, self.log) as context:
                    providers = list(self.layout_providers_store.get(
                        context, tenant_name))
                    self.tenant_providers[tenant_name] = providers
                    for provider in providers:
                        self.log.debug("Loaded provider %s", provider.name)
                self.local_layout_state[tenant_name] = layout_state
                updated = True
            else:
                self.tenant_providers.pop(tenant_name, None)
                self.local_layout_state.pop(tenant_name, None)
        return updated

    def addImageBuildEvent(self, tenant_name, project_canonical_name,
                           branch, image_names):
        project_hostname, project_name = \
            project_canonical_name.split('/', 1)
        driver = self.connections.drivers['zuul']
        event = driver.getImageBuildEvent(
            list(image_names), project_hostname, project_name, branch)
        self.log.info("Submitting image build event for %s %s",
                      tenant_name, image_names)
        self.trigger_events[tenant_name].put(event.trigger_name, event)

    def addImageValidateEvent(self, image_upload):
        iba = self.image_build_registry.getItem(image_upload.artifact_uuid)
        project_hostname, project_name = \
            iba.project_canonical_name.split('/', 1)
        tenant_name = iba.build_tenant_name
        driver = self.connections.drivers['zuul']
        event = driver.getImageValidateEvent(
            [iba.name], project_hostname, project_name, iba.project_branch,
            image_upload.uuid)
        self.log.info("Submitting image validate event for %s %s",
                      tenant_name, iba.name)
        self.trigger_events[tenant_name].put(event.trigger_name, event)

    def addImageDeleteEvent(self, iba):
        project_hostname, project_name = \
            iba.project_canonical_name.split('/', 1)
        tenant_name = iba.build_tenant_name
        driver = self.connections.drivers['zuul']
        event = driver.getImageDeleteEvent(
            [iba.name], project_hostname, project_name, iba.project_branch,
            iba.uuid)
        self.log.info("Submitting image delete event for %s %s",
                      tenant_name, iba.name)
        self.trigger_events[tenant_name].put(event.trigger_name, event)

    def checkMissingImages(self):
        for tenant_name, providers in self.tenant_providers.items():
            images_by_project_branch = {}
            for provider in providers:
                for image in provider.images.values():
                    if image.type == 'zuul':
                        self.checkMissingImage(tenant_name, image,
                                               images_by_project_branch)
            for ((project_canonical_name, branch), image_names) in \
                images_by_project_branch.items():
                self.addImageBuildEvent(tenant_name, project_canonical_name,
                                        branch, image_names)

    def checkMissingImage(self, tenant_name, image, images_by_project_branch):
        # If there is already a successful build for
        # this image, skip.
        self.log.debug("Checking for missing images")
        seen_formats = set()
        for iba in self.image_build_registry.getArtifactsForImage(
                image.canonical_name):
            seen_formats.add(iba.format)

        if image.format in seen_formats:
            # We have at least one build with the required
            # formats
            return

        # Collect images with the same project-branch so we can build
        # them in one buildset.
        key = (image.project_canonical_name, image.branch)
        images = images_by_project_branch.setdefault(key, set())
        images.add(image.name)

    def checkOldImages(self):
        self.log.debug("Checking for old images")
        self.upload_deleted_event.clear()
        keep_uploads = set()
        for tenant_name, providers in self.tenant_providers.items():
            for provider in providers:
                for image in provider.images.values():
                    if image.type == 'zuul':
                        self.checkOldImage(tenant_name, provider, image,
                                           keep_uploads)

        uploads_by_artifact = collections.defaultdict(list)
        latest_upload_timestamp = 0
        for upload in self.image_upload_registry.getItems():
            if upload.timestamp > latest_upload_timestamp:
                latest_upload_timestamp = upload.timestamp
            uploads_by_artifact[upload.artifact_uuid].append(upload)
            iba = self.image_build_registry.getItem(upload.artifact_uuid)
            if (iba.state == model.STATE_DELETING or
                upload.state == model.STATE_DELETING or
                (upload.state == model.STATE_READY and
                 upload not in keep_uploads)):
                self.upload_executor.submit(DeleteJob(self, iba, upload).run)
        for iba in self.image_build_registry.getItems():
            if iba.state not in (model.STATE_DELETING, model.STATE_READY):
                continue
            if (iba.timestamp > latest_upload_timestamp or
                not latest_upload_timestamp):
                # Ignore artifacts that are newer than the newest upload
                continue
            if len(uploads_by_artifact[iba.uuid]) == 0:
                self.log.info("Deleting image build artifact "
                              "with no uploads: %s", iba)
                with self.createZKContext(None, self.log) as ctx:
                    try:
                        with iba.locked(ctx, blocking=False):
                            iba.delete(ctx)
                    except LockException:
                        pass

    def checkOldImage(self, tenant_name, provider, image,
                      keep_uploads):
        self.log.debug("Checking for old artifacts for image %s",
                       image.canonical_name)
        image_cname = image.canonical_name
        uploads = self.image_upload_registry.getUploadsForImage(image_cname)
        valid_uploads = [
            upload for upload in uploads
            if (provider.canonical_name in upload.providers and
                upload.validated and
                upload.external_id)
        ]
        # Keep the 2 most recent (uploads are already sorted by timestamp)
        keep_uploads.update(set(valid_uploads[-2:]))

    def checkMissingUploads(self):
        self.log.debug("Checking for missing uploads")
        uploads_by_artifact_id = collections.defaultdict(list)
        self.upload_added_event.clear()
        for upload in self.image_upload_registry.getItems():
            if upload.endpoint_name not in self.endpoints:
                continue
            iba = self.image_build_registry.getItem(upload.artifact_uuid)
            if iba.state == model.STATE_DELETING:
                continue
            if upload.state != model.STATE_PENDING:
                continue
            upload_list = uploads_by_artifact_id[upload.artifact_uuid]
            upload_list.append(upload)

        for artifact_uuid, uploads in uploads_by_artifact_id.items():
            iba = self.image_build_registry.getItem(artifact_uuid)
            self.upload_executor.submit(UploadJob(self, iba, uploads).run)

    def _downloadArtifactChunk(self, url, start, end, path):
        headers = {'Range': f'bytes={start}-{end}'}
        with open(path, 'r+b') as f:
            f.seek(start)
            with requests.get(url, stream=True, headers=headers) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_BLOCK_SIZE):
                    f.write(chunk)

    def downloadArtifact(self, image_build_artifact):
        path = os.path.join(self.temp_dir, image_build_artifact.uuid)
        self.log.info("Downloading artifact %s into %s",
                      image_build_artifact, path)
        futures = []
        with requests.head(image_build_artifact.url) as resp:
            size = int(resp.headers['content-length'])
        with open(path, 'wb') as f:
            f.truncate(size)
        with ThreadPoolExecutor(max_workers=5) as executor:
            for start in range(0, size, DOWNLOAD_CHUNK_SIZE):
                end = start + DOWNLOAD_CHUNK_SIZE - 1
                futures.append(executor.submit(self._downloadArtifactChunk,
                                               image_build_artifact.url,
                                               start, end, path))
            for future in concurrent.futures.as_completed(futures):
                future.result()
        self.log.debug("Downloaded %s bytes to %s", size, path)
        if path.endswith('.zst'):
            subprocess.run(["zstd", "-dq", path],
                           cwd=self.temp_dir, check=True, capture_output=True)
            path = path[:-len('.zst')]
            self.log.debug("Decompressed image to %s", path)
        return path

    def getImageExternalId(self, node, provider):
        label = provider.labels[node.label]
        image = provider.images[label.image]
        if image.type != 'zuul':
            return None
        image_cname = image.canonical_name
        uploads = self.image_upload_registry.getUploadsForImage(image_cname)
        # TODO: we could also check config hash here to start using an
        # image that wasn't originally attached to this provider.
        valid_uploads = [
            upload for upload in uploads
            if (provider.canonical_name in upload.providers and
                upload.validated and
                upload.external_id)
        ]
        if not valid_uploads:
            raise Exception("No image found")
        # Uploads are already sorted by timestamp
        image_upload = valid_uploads[-1]
        return image_upload.external_id
