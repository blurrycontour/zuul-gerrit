# Copyright 2023 Acme Gating, LLC
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

import abc
import json
import logging
import queue
import threading
import time

from kazoo import exceptions as kze
from kazoo.protocol.states import (
    EventType,
    WatchedEvent,
    KazooState,
)

from zuul.zk.vendor.states import AddWatchMode


class ZuulTreeCache(abc.ABC):
    '''
    Use watchers to keep a cache of local objects up to date.
    '''

    log = logging.getLogger("zuul.zk.ZooKeeper")
    event_log = logging.getLogger("zuul.zk.cache.event")
    qsize_warning_threshold = 1024

    def __init__(self, zk_client, root):
        self.client = zk_client.client
        self.root = root
        self._last_event_warning = time.monotonic()
        self._last_playback_warning = time.monotonic()
        self._cached_objects = {}
        self._cached_paths = set()
        self._ready = threading.Event()
        self._init_lock = threading.Lock()
        self._stopped = False
        self._stop_workers = False
        self._event_queue = queue.Queue()
        self._playback_queue = queue.Queue()
        self._event_worker = None
        self._playback_worker = None

        self.client.add_listener(self._sessionListener)
        self._start()

    def _bytesToDict(self, data):
        return json.loads(data.decode('utf8'))

    def _sessionListener(self, state):
        if state == KazooState.LOST:
            self._ready.clear()
            self._stop_workers = True
            self._event_queue.put(None)
            self._playback_queue.put(None)
        elif state == KazooState.CONNECTED and not self._stopped:
            self.client.handler.short_spawn(self._start)

    def _cacheListener(self, event):
        self._event_queue.put(event)

    def _start(self):
        with self._init_lock:
            self.log.debug("Initialize cache at %s", self.root)

            self._ready.clear()
            self._stop_workers = True
            self._event_queue.put(None)
            self._playback_queue.put(None)

            # If we have an event worker (this is a re-init), then wait
            # for it to finish stopping.
            if self._event_worker:
                self._event_worker.join()
            # Replace the queue since any events from the previous
            # session aren't valid.
            self._event_queue = queue.Queue()
            # Prepare (but don't start) the new worker.
            self._event_worker = threading.Thread(
                target=self._eventWorker)
            self._event_worker.daemon = True

            if self._playback_worker:
                self._playback_worker.join()
            self._playback_queue = queue.Queue()
            self._playback_worker = threading.Thread(
                target=self._playbackWorker)
            self._playback_worker.daemon = True

            # Clear the stop flag and start the workers now that we
            # are sure that both have stopped and we have cleared the
            # queues.
            self._stop_workers = False
            self._event_worker.start()
            self._playback_worker.start()

            try:
                self.client.add_watch(
                    self.root, self._cacheListener,
                    AddWatchMode.PERSISTENT_RECURSIVE)
                self.client.ensure_path(self.root)
                self._walkTree()
                self._ready.set()
                self.log.debug("Cache at %s is ready", self.root)
            except Exception:
                self.log.exception("Error initializing cache at %s", self.root)
                self.client.handler.short_spawn(self._start)

    def stop(self):
        self._stopped = True
        self._event_queue.put(None)
        self._playback_queue.put(None)

    def _walkTree(self, root=None, seen_paths=None):
        # Recursively walk the tree and emit fake changed events for
        # every item in zk and fake deleted events for every item in
        # the cache that is not in zk
        exists = True
        am_root = False
        if root is None:
            am_root = True
            root = self.root
            seen_paths = set()
            if not self.client.exists(root):
                exists = False
        if exists:
            seen_paths.add(root)
            event = WatchedEvent(EventType.NONE,
                                 self.client._state,
                                 root)
            self._cacheListener(event)
            try:
                for child in self.client.get_children(root):
                    safe_root = root
                    if safe_root == '/':
                        safe_root = ''
                    new_path = '/'.join([safe_root, child])
                    self._walkTree(new_path, seen_paths)
            except kze.NoNodeError:
                self.log.debug("Can't sync non-existent node %s", root)
        if am_root:
            for path in self._cached_paths.copy():
                if path not in seen_paths:
                    event = WatchedEvent(
                        EventType.NONE,
                        self.client._state,
                        path)
                    self._cacheListener(event)

    def _eventWorker(self):
        while not (self._stopped or self._stop_workers):
            event = self._event_queue.get()
            if event is None:
                self._event_queue.task_done()
                continue

            qsize = self._event_queue.qsize()
            if qsize > self.qsize_warning_threshold:
                now = time.monotonic()
                if now - self._last_event_warning > 60:
                    self.log.warning("Event queue size for cache at %s is %s",
                                     self.root, qsize)
                    self._last_event_warning = now

            try:
                self._handleCacheEvent(event)
            except Exception:
                self.log.exception("Error handling event %s:", event)
            self._event_queue.task_done()

    def _handleCacheEvent(self, event):
        # Ignore root node since we don't maintain a cached object for
        # it (all cached objects are under the root in our tree
        # caches).
        if event.path == self.root:
            return

        # Start by assuming we need to fetch data for the event.
        fetch = True
        if event.type == EventType.NONE:
            if event.path is None:
                # We're probably being told of a connection change; ignore.
                return
        elif (event.type == EventType.DELETED):
            # If this is a normal deleted event, we don't need to
            # fetch anything.
            fetch = False

        key = self.parsePath(event.path)
        if key is None and event.type != EventType.NONE:
            # The cache doesn't care about this path, so we don't need
            # to fetch (unless the type is none (re-initialization) in
            # which case we always need to fetch in order to determine
            # existence).
            fetch = False

        if fetch:
            future = self.client.get_async(event.path)
        else:
            future = None
        self._playback_queue.put((event, future, key))

    def _playbackWorker(self):
        while not (self._stopped or self._stop_workers):
            item = self._playback_queue.get()
            if item is None:
                self._playback_queue.task_done()
                continue

            qsize = self._playback_queue.qsize()
            if qsize > self.qsize_warning_threshold:
                now = time.monotonic()
                if now - self._last_playback_warning > 60:
                    self.log.warning(
                        "Playback queue size for cache at %s is %s",
                        self.root, qsize)
                    self._last_playback_warning = now

            event, future, key = item
            try:
                self._handlePlayback(event, future, key)
            except Exception:
                self.log.exception("Error playing back event %s:", event)
            self._playback_queue.task_done()

    def _handlePlayback(self, event, future, key):
        self.event_log.debug("Cache playback event %s", event)
        exists = None
        data, stat = None, None

        if future:
            try:
                data, stat = future.get()
                exists = True
            except kze.NoNodeError:
                exists = False

        # We set "exists" above in case of cache re-initialization,
        # which happens out of sequence with the normal watch events.
        # and we can't be sure whether the node still exists or not by
        # the time we process it.  Later cache watch events may
        # supercede this (for example, we may process a NONE event
        # here which we interpret as a delete which may be followed by
        # a normal delete event.  That case, and any other variations
        # should be anticipated.

        # If the event tells us whether the node exists, prefer that
        # value, otherwise fallback to what we determined above.
        if (event.type in (EventType.CREATED, EventType.CHANGED)):
            exists = True
        elif (event.type == EventType.DELETED):
            exists = False

        # Keep the cached paths up to date
        if exists:
            self._cached_paths.add(event.path)
        else:
            self._cached_paths.discard(event.path)

        # Some caches have special handling for certain sub-objects
        self.preCacheHook(event, exists)

        # If we don't actually cache this kind of object, return now
        if key is None:
            return

        obj = None
        if data:
            # Perform an in-place update of the cached object if possible
            old_obj = self._cached_objects.get(key)
            if old_obj:
                if stat.mzxid <= old_obj._zstat.mzxid:
                    # Don't update to older data
                    return
                if getattr(old_obj, 'lock', None):
                    # Don't update a locked object
                    return
                old_obj._updateFromRaw(data, stat)
            else:
                obj = self.objectFromDict(data, stat)
                self._cached_objects[key] = obj
        else:
            try:
                obj = self._cached_objects[key]
                del self._cached_objects[key]
            except KeyError:
                # If it's already gone, don't care
                pass
        self.postCacheHook(event, data, stat, key, obj)

    def ensureReady(self):
        self._ready.wait()

    # Methods for subclasses:
    def preCacheHook(self, event, exists):
        """Called before the cache is updated

        This is called for any add/update/remove event under the root,
        even for paths that are ignored, so users much test the
        relevance of the path in this method.

        The ``exists`` argument is provided in all cases. In the case
        of EventType.NONE events, it indicates whether the cache has
        seen the node in ZK immediately before calling this method.
        Otherwise, it indicates whether or not the EventType would
        cause the node to exist in ZK.

        :param EventType event: The event.
        :param bool exists: Whether the object exists in ZK.

        """
        return None

    def postCacheHook(self, event, data, stat, key, obj):
        """Called after the cache has been updated"""
        return None

    @abc.abstractmethod
    def parsePath(self, path):
        """Parse the path and return a cache key

        The cache key is an opaque object ignored by the cache, but
        must be hashable.

        A convention is to use a tuple of relevant path components as
        the key.

        Return None to indicate the path is not relevant to the cache.

        """
        return None

    @abc.abstractmethod
    def objectFromDict(self, d, key):
        """Construct an object from ZooKeeper data

        Given a dictionary of data from ZK and cache key, construct
        and return an object to insert into the cache.

        :param dict d: The dictionary.
        :param object key: The key as returned by parsePath.
        """
        pass
