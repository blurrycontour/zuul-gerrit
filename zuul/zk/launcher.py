# Copyright 2024 BMW Group
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

import mmh3
from kazoo.exceptions import LockTimeout, NoNodeError

from zuul.model import NodesetRequest, ProviderNode
from zuul.zk.cache import ZuulTreeCache
from zuul.zk.locks import SessionAwareLock


def _dictToBytes(data):
    return json.dumps(data).encode("utf-8")


def _bytesToDict(raw_data):
    return json.loads(raw_data.decode("utf-8"))


def launcher_score(name, item):
    return mmh3.hash(f"{name}-{item.uuid}", signed=False)


class RequestCache(ZuulTreeCache):
    REQUESTS_PATH = "requests"
    LOCKS_PATH = "locks"

    def __init__(self, zk_client, root, updated_event):
        self.updated_event = updated_event
        super().__init__(zk_client, root)

    def _parsePath(self, path):
        if not path.startswith(self.root):
            return None
        path = path[len(self.root) + 1:]
        parts = path.split('/')
        # We are interested in requests with a parts that look like:
        # ([requests, locks], <uuid>, ...)
        if len(parts) < 2:
            return None
        return parts

    def parsePath(self, path):
        parts = self._parsePath(path)
        if parts is None:
            return None
        if len(parts) != 2:
            return None
        if parts[0] != self.REQUESTS_PATH:
            return None
        request_uuid = parts[-1]
        return (request_uuid,)

    def preCacheHook(self, event, exists):
        parts = self._parsePath(event.path)
        if parts is None:
            return

        # Expecting (locks, <uuid>, <lock>,)
        if len(parts) != 3:
            return

        object_type, request_uuid, *_ = parts
        if object_type != self.LOCKS_PATH:
            return

        key = (request_uuid,)
        request = self._cached_objects.get(key)

        if not request:
            return

        self.updated_event()
        request._set(is_locked=exists)

    def postCacheHook(self, event, data, stat):
        self.updated_event()

    def objectFromDict(self, d, key):
        return NodesetRequest.fromDict(d)

    def getRequest(self, request_id):
        self.ensureReady()
        return self._cached_objects.get((request_id,))

    def getRequests(self):
        # get a copy of the values view to avoid runtime errors in the event
        # the _cached_nodes dict gets updated while iterating
        self.ensureReady()
        return list(self._cached_objects.values())


class ProviderCache(ZuulTreeCache):
    NODES_PATH = "nodes"
    LOCKS_PATH = "locks"

    def __init__(self, zk_client, root, updated_event, provider_filter=None):
        self.updated_event = updated_event
        self.provider_filter = set(
            provider_filter) if provider_filter else set()
        super().__init__(zk_client, root)

    def _getCachedByType(self, object_type):
        cached_objects = list(self._cached_objects.items())
        return [o for k, o in cached_objects.items()
                if k.object_type == object_type]

    def _keyFromNode(self, node):
        return (node.provider, node.uuid,)

    # def getLockPath(self, node):
    #     return f"{self.root}/{node.provider}/{self.LOCKS_PATH}/{node.uuid}"

    def _parsePath(self, path):
        if not path.startswith(self.root):
            return None
        path = path[len(self.root) + 1:]
        parts = path.split('/')
        # We are interested in provider nodes with a parts that look like:
        # (<provider>, [nodes, locks], <node>, ...)
        if len(parts) < 3:
            return None
        return parts

    def parsePath(self, path):
        parts = self._parsePath(path)
        if parts is None:
            return None

        if len(parts) != 3:
            # TODO: handle potential sub-nodes here
            return None

        provider, object_type, node = parts
        if object_type != self.NODES_PATH:
            return None

        if self.provider_filter and provider not in self.provider_filter:
            return None

        return (provider, node,)

    def preCacheHook(self, event, exists):
        parts = self._parsePath(event.path)
        if parts is None:
            return

        # Expecting (<provider>, locks, <uuid>, <lock>,)
        if len(parts) != 4:
            return

        provider, object_type, node_uuid, *_ = parts
        if object_type != self.LOCKS_PATH:
            return

        key = (provider, node_uuid,)
        node = self._cached_objects.get(key)

        if not node:
            return

        self.updated_event()
        node._set(is_locked=exists)

    def postCacheHook(self, event, data, stat):
        self.updated_event()

    def objectFromDict(self, d, key):
        node = ProviderNode.fromDict(d)
        node.provider = key[0]
        return node

    def getNode(self, path):
        self.ensureReady()
        key = self.parsePath(path)
        return self._cached_objects.get(key)

    def getNodes(self):
        # get a copy of the values view to avoid runtime errors in the event
        # the _cached_nodes dict gets updated while iterating
        self.ensureReady()
        return list(self._cached_objects.values())


class LauncherApi:
    log = logging.getLogger("zuul.LauncherApi")

    NODESET_ROOT = "/zuul/nodeset"
    PROVIDER_ROOT = "/zuul/provider"

    def __init__(self, zk_client):
        self.zk_client = zk_client

    def submitNodesetRequest(self, request):
        self.zk_client.client.create(
            self._getRequestPath(request),
            _dictToBytes(request.toDict()),
            makepath=True)

    def removeNodesetRequest(self, request):
        # FIXME: do we have to deal with NodeNotEmpty errors here as well?
        try:
            self.zk_client.client.delete(
                self._getRequestPath(request), recursive=True)
        except NoNodeError:
            # Node is already deleted
            pass

    def refreshNodesetRequest(self, request):
        raw, stat = self.zk_client.client.get(self._getRequestPath(request))
        request.updateFromDict(self._bytesToDict(raw))
        request.stat = stat

    def lockRequest(self, request, blocking=True, timeout=None):
        path = self._getRequestLockPath(request)
        return self._lock(request, path, blocking, timeout)

    def unlockRequest(self, request):
        if request.lock is None:
            self.log.warning("Request %s does not hold a lock", request)
        else:
            self._unlock(request)

    def updateNodesetRequest(self, request, **attrs):
        if not request.lock:
            raise RuntimeError("Can't update request without a lock")
        if not request.stat:
            raise RuntimeError("Can't update request without version info")
        version = request.stat.version
        request._set(**attrs)
        zstat = self.zk_client.client.set(
            self._getRequestPath(request),
            _dictToBytes(request.toDict()),
            version=version
        )
        request.stat = zstat

    def requestProviderNode(self, provider, node):
        path, zstat = self.zk_client.client.create(
            self._getNodePath(provider, node),
            _dictToBytes(node.toDict()),
            makepath=True, include_data=True)
        node.path, node.stat, node.provider = path, zstat, provider

    def lockNode(self, node, blocking=True, timeout=None):
        path = self._getNodeLockPath(node)
        return self._lock(node, path, blocking, timeout)

    def unlockNode(self, node):
        if node.lock is None:
            self.log.warning("Node %s does not hold a lock", node)
        else:
            self._unlock(node)

    def updateNode(self, node, **attrs):
        if not node.lock:
            raise RuntimeError("Can't update node without a lock")
        if not node.stat:
            raise RuntimeError("Can't update node without version info")
        version = node.stat.version
        node._set(**attrs)
        zstat = self.zk_client.client.set(
            node.path,
            _dictToBytes(node.toDict()),
            version=version
        )
        node.stat = zstat

    def _getRequestLockPath(self, request):
        return f"{self.NODESET_ROOT}/{ProviderCache.LOCKS_PATH}/{request.uuid}"

    def _getRequestPath(self, request):
        return (
            f"{self.NODESET_ROOT}/{RequestCache.REQUESTS_PATH}/{request.uuid}")

    def _getNodePath(self, provider, node):
        return (
            f"{self.PROVIDER_ROOT}/{provider}/"
            f"{ProviderCache.NODES_PATH}/{node.uuid}"
        )

    def _getNodeLockPath(self, node):
        return (
            f"{self.PROVIDER_ROOT}/{node.provider}/"
            f"{ProviderCache.LOCKS_PATH}/{node.uuid}"
        )

    def _lock(self, obj, path, blocking=True, timeout=None):
        have_lock = False
        lock = None
        try:
            lock = SessionAwareLock(self.zk_client.client, path)
            have_lock = lock.acquire(blocking, timeout)
        except NoNodeError:
            # Request disappeared
            have_lock = False
        except LockTimeout:
            have_lock = False
            self.log.error("Timeout trying to acquire lock: %s", path)

        # If we aren't blocking, it's possible we didn't get the lock
        # because someone else has it.
        if not have_lock:
            return False

        obj.lock = lock
        return True

    def _unlock(self, obj):
        obj.lock.release()
        obj.lock = None


class LauncherServerApi(LauncherApi):
    log = logging.getLogger("zuul.LauncherServerApi")

    def __init__(self, zk_client, component_registry, component_info,
                 event_callback=None, provider_filter=None):
        super().__init__(zk_client)
        self.component_registry = component_registry
        self.component_info = component_info
        self.event_callback = event_callback
        self.request_cache = RequestCache(
            self.zk_client, self.NODESET_ROOT, self.event_callback)
        self.provider_cache = ProviderCache(
            self.zk_client, self.PROVIDER_ROOT, self.event_callback)

    def stop(self):
        self.request_cache.stop()
        self.provider_cache.stop()

    def getMatchingRequests(self):
        candidate_launchers = {
            c.hostname: c for c in self.component_registry.all("launcher")}
        candidate_names = set(candidate_launchers.keys())

        for request in self.request_cache.getRequests():
            if request.lock:
                if request.lock.is_still_valid():
                    # We are holding a lock, so short-circuit here.
                    yield request
                else:
                    self.log.debug("Resetting lost lock for request %s",
                                   request)
                    self._unlock(request)
            if request.is_locked:
                # Request is locked by someone else
                continue

            score_launchers = (
                set(request._lscores.keys()) if request._lscores else set())
            missing_scores = candidate_names - score_launchers
            if missing_scores or request._lscores is None:
                # (Re-)compute launcher scores
                request._lscores = {launcher_score(n, request): n
                                    for n in candidate_names}

            launcher_scores = sorted(request._lscores.items())
            # self.log.debug("Launcher scores: %s", launcher_scores)
            for score, launcher_name in launcher_scores:
                launcher = candidate_launchers.get(launcher_name)
                if not launcher:
                    continue
                if not launcher.state != launcher.RUNNING:
                    continue
                if launcher.hostname == self.component_info.hostname:
                    yield request
                break

    def getNodesetRequest(self, request_id):
        return self.request_cache.getRequest(request_id)

    def getNodesetRequests(self):
        return self.request_cache.getRequests()

    def getMatchingProviderNodes(self):
        all_launchers = {
            c.hostname: c for c in self.component_registry.all("launcher")}

        for node in self.provider_cache.getNodes():
            if node.lock:
                # We are holding a lock, so short-circuit here.
                yield node
            if node.is_locked:
                # Node is locked by someone else
                continue

            candidate_launchers = {n: c for n, c in all_launchers.items()
                                   if not c.providers
                                   or node.provider in c.providers}
            candidate_names = set(candidate_launchers)
            if node._lscores is None:
                missing_scores = candidate_names
            else:
                score_launchers = set(node._lscores.keys())
                missing_scores = candidate_names - score_launchers

            if missing_scores or node._lscores is None:
                # (Re-)compute launcher scores
                node._lscores = {launcher_score(n, node): n
                                 for n in candidate_names}

            launcher_scores = sorted(node._lscores.items())

            for score, launcher_name in launcher_scores:
                launcher = candidate_launchers.get(launcher_name)
                if not launcher:
                    # Launcher is no longer online
                    continue
                if not launcher.state != launcher.RUNNING:
                    continue
                if launcher.hostname == self.component_info.hostname:
                    yield node
                break

    def getProviderNode(self, path):
        return self.provider_cache.getNode(path)

    def getProviderNodes(self):
        return self.provider_cache.getNodes()

    def cleanupNodes(self):
        # TODO: This method currently just performs some basic cleanup and
        # might need to be extended in the future.
        for node in self.getProviderNodes():
            if node.state != ProviderNode.State.USED:
                continue
            if node.is_locked:
                continue
            if self.getNodesetRequest(node.request_id):
                continue
            if self.lockNode(node):
                try:
                    self.zk_client.client.delete(node.path, recursive=True)
                except NoNodeError:
                    # Node is already deleted
                    pass
                finally:
                    self.unlockNode(node)
