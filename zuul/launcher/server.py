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
import collections
import itertools
import logging
import os
import random
import socket
import threading
import time
import uuid

import requests

from zuul import model
from zuul.lib import commandsocket, tracing
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


class NodesetRequestError(Exception):
    """Errors that should lead to the request being declined."""
    pass


class ProviderNodeError(Exception):
    """Errors that should lead to the provider node being failed."""
    pass


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
        try:
            try:
                with self.image_build_artifact.locked(
                        self.launcher.zk_client, blocking=False):
                    for upload in self.uploads:
                        if upload.acquireLock(
                                self.launcher.zk_client, blocking=False):
                            acquired.append(upload)
            except LockException:
                return

            if not acquired:
                return

            path = self.launcher.downloadArtifact(self.image_build_artifact)
            futures = []
            for upload in acquired:
                future = self.launcher.endpoint_upload_executor.submit(
                    EndpointUploadJob(self.launcher, self.image_build_artifact,
                                      upload, path).run)
                futures.append((upload, future))
            for upload, future in futures:
                try:
                    future.result()
                except Exception:
                    self.log.exception("Unable to upload image %s", upload)
        finally:
            for upload in acquired:
                try:
                    upload.releaseLock()
                except Exception:
                    self.log.exception("Unable to release lock for %s", upload)
            if path:
                try:
                    os.unlink(path)
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
        external_id = provider.uploadImage(
            provider_image, self.path, self.artifact.format, metadata,
            self.artifact.md5sum, self.artifact.sha256)
        with self.launcher.createZKContext(self.upload._lock, self.log) as ctx:
            self.upload.updateAttributes(
                ctx,
                external_id=external_id,
                timestamp=time.time())
        self.launcher.addImageValidateEvent(self.upload)


class Launcher:
    log = logging.getLogger("zuul.Launcher")
    # Max. time the main event loop is allowed to sleep
    MAX_SLEEP = 1

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
                self.checkMissingImages()
                self.checkMissingUploads()
        if self.upload_added_event.is_set():
            self.checkMissingUploads()
        self._processRequests()
        self._processNodes()

    def _processRequests(self):
        for request in self.api.getMatchingRequests():
            log = get_annotated_logger(self.log, request, request=request.uuid)
            if not request.hasLock():
                if request.state in request.FINAL_STATES:
                    # Nothing to do here
                    continue
                log.debug("Got request %s", request)
                if not request.acquireLock(self.zk_client, blocking=False):
                    log.debug("Failed to lock matching request %s", request)
                    continue

            if not self._cachesReadyForRequest(request):
                self.log.debug("Caches are not up-to-date for %s", request)
                continue

            try:
                if request.state == model.NodesetRequest.State.REQUESTED:
                    self._acceptRequest(request, log)
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
                request.releaseLock()

    def _cachesReadyForRequest(self, request):
        # Make sure we have all associated provider nodes in the cache
        return all(
            self.api.getProviderNode(n)
            for n in itertools.chain.from_iterable(request.provider_nodes)
        )

    def _acceptRequest(self, request, log):
        log.debug("Accepting request %s", request)
        # Create provider nodes for the requested labels
        provider_nodes = []
        label_providers = self._selectProviders(request, log)
        with self.createZKContext(request._lock, log) as ctx:
            for i, (label_name, provider) in enumerate(label_providers):
                node = self._requestNode(
                    label_name, request, provider, log, ctx)
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
        for i, label in enumerate(request.labels):
            candidate_providers = [
                p for p in providers
                if p.hasLabel(label)
                and provider_failures[p.name] < p.launch_attempts
            ]
            if not candidate_providers:
                raise NodesetRequestError(
                    f"No provider found for label {label}")

            log.debug("Candidate providers: %s", candidate_providers)
            # TODO: make provider selection more sophisticated
            label_providers.append((label, random.choice(candidate_providers)))
        return label_providers

    def _requestNode(self, label_name, request, provider, log, ctx):
        # Create a deterministic node UUID by using
        # the request UUID as namespace.
        node_uuid = uuid.uuid4().hex
        label = provider.labels[label_name]
        tags = provider.getNodeTags(
            self.system.system_id, request, provider, label,
            node_uuid)
        node_class = provider.driver.getProviderNodeClass()
        node = node_class.new(
            ctx,
            uuid=node_uuid,
            label=label_name,
            request_id=request.uuid,
            connection_name=provider.connection_name,
            tenant_name=request.tenant_name,
            provider=provider.name,
            tags=tags,
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
                label_name, provider = label_providers[i]
                log.info("Retrying request with provider %s", provider)
                with self.createZKContext(request._lock, log) as ctx:
                    node = self._requestNode(
                        label_name, request, provider, log, ctx)
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
                if node.is_locked:
                    continue

                # There is an associated nodeset request and we can't advance
                # the node state.
                if (self.api.getNodesetRequest(node.request_id)
                        and node.state not in node.LAUNCHER_STATES):
                    continue

                if not node.acquireLock(self.zk_client, blocking=False):
                    log.debug("Failed to lock matching node %s", node)
                    continue

            if request := self.api.getNodesetRequest(node.request_id):
                try:
                    if node.state in node.CREATE_STATES:
                        self._checkNode(node, log)
                    if node.state == model.ProviderNode.State.READY:
                        node.releaseLock()
                except Exception:
                    state = model.ProviderNode.State.FAILED
                    log.exception("Marking node %s as %s", node, state)
                    with self.createZKContext(node._lock, self.log) as ctx:
                        node.updateAttributes(ctx, state=state)

            # TODO: implement node re-use
            # * deallocate from request here
            # * re-allocated similar to min-ready
            if not request or node.state in node.State.FAILED:
                self._cleanupNode(node, log)

    def _checkNode(self, node, log):
        with self.createZKContext(node._lock, self.log) as ctx:
            with node.activeContext(ctx):
                if not node.create_state_machine:
                    log.debug("Building node %s", node)
                    provider = self._getProvider(
                        node.tenant_name, node.provider)
                    image_external_id = self.getImageExternalId(node, provider)
                    log.debug("Node %s external id %s",
                              node, image_external_id)
                    node.create_state_machine = provider.getCreateStateMachine(
                        node, image_external_id, log)

                log.debug("Checking node %s", node)
                node.create_state_machine.advance()
                if not node.create_state_machine.complete:
                    self.wake_event.set()
                    return
                node.state = model.ProviderNode.State.READY
                log.debug("Marking node %s as %s", node, node.state)
        node.releaseLock()

    def _cleanupNode(self, node, log):
        with self.createZKContext(node._lock, self.log) as ctx:
            with node.activeContext(ctx):
                if not node.delete_state_machine:
                    log.debug("Cleaning up node %s", node)
                    provider = self._getProvider(
                        node.tenant_name, node.provider)
                    node.delete_state_machine = provider.getDeleteStateMachine(
                        node, log)

                log.debug("Checking node %s cleanup", node)
                node.delete_state_machine.advance()

            if not node.delete_state_machine.complete:
                self.wake_event.set()
                return

            if not self.api.getNodesetRequest(node.request_id):
                log.debug("Removing provider node %s", node)
                node.delete(ctx)
                node.releaseLock()

    def _getProvider(self, tenant_name, provider_name):
        for provider in self.tenant_providers[tenant_name]:
            if provider.name == provider_name:
                return provider
        raise ProviderNodeError(
            f"Unable to find {provider_name} in tenant {tenant_name}")

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
        for build in self.image_build_registry.getArtifactsForImage(
                image.canonical_name):
            seen_formats.add(build.format)

        if image.format in seen_formats:
            # We have at least one build with the required
            # formats
            return

        # Collect images with the same project-branch so we can build
        # them in one buildset.
        key = (image.project_canonical_name, image.branch)
        images = images_by_project_branch.setdefault(key, set())
        images.add(image.name)

    def checkMissingUploads(self):
        self.log.debug("Checking for missing uploads")
        uploads_by_artifact_id = collections.defaultdict(list)
        self.upload_added_event.clear()
        for upload in self.image_upload_registry.getItems():
            self.log.debug("Checking %s", upload)
            if upload.external_id:
                continue
            if upload.endpoint_name not in self.endpoints:
                continue
            upload_list = uploads_by_artifact_id[upload.artifact_uuid]
            upload_list.append(upload)

        for artifact_uuid, uploads in uploads_by_artifact_id.items():
            iba = self.image_build_registry.getItem(artifact_uuid)
            self.upload_executor.submit(UploadJob(self, iba, uploads).run)

    def downloadArtifact(self, image_build_artifact):
        path = os.path.join(self.temp_dir, image_build_artifact.uuid)
        # TODO: verify checksum here
        with open(path, 'wb') as f:
            with requests.get(image_build_artifact.url, stream=True) as resp:
                for chunk in resp.iter_content(chunk_size=1024 * 8):
                    f.write(chunk)
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
