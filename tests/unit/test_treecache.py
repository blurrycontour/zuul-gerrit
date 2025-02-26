# Copyright 2024-2025 Acme Gating, LLC
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

from zuul.zk import ZooKeeperClient
from zuul.zk.cache import ZuulTreeCache
from zuul.zk.components import (
    ComponentRegistry,
    COMPONENT_REGISTRY
)
from tests.base import (
    BaseTestCase,
    iterate_timeout,
    ZOOKEEPER_SESSION_TIMEOUT,
)

from kazoo.protocol.states import KazooState


class SimpleTreeCacheObject:
    def __init__(self, key, data, zstat):
        self.key = key
        self.data = json.loads(data)
        self._zstat = zstat
        self.path = '/'.join(key)

    def _updateFromRaw(self, data, zstat, context=None):
        self.data = json.loads(data)
        self._zstat = zstat


class SimpleTreeCache(ZuulTreeCache):
    def objectFromRaw(self, key, data, zstat):
        return SimpleTreeCacheObject(key, data, zstat)

    def updateFromRaw(self, obj, key, data, zstat):
        obj._updateFromRaw(data, zstat, None)

    def parsePath(self, path):
        return tuple(path.split('/'))


class TestTreeCache(BaseTestCase):
    # A very simple smoke test of the tree cache

    def setUp(self):
        super().setUp()

        self.setupZK()

        self.zk_client = ZooKeeperClient(
            self.zk_chroot_fixture.zk_hosts,
            tls_cert=self.zk_chroot_fixture.zookeeper_cert,
            tls_key=self.zk_chroot_fixture.zookeeper_key,
            tls_ca=self.zk_chroot_fixture.zookeeper_ca,
            timeout=ZOOKEEPER_SESSION_TIMEOUT,
        )
        self.addCleanup(self.zk_client.disconnect)
        self.zk_client.connect()
        self.setupModelPin()
        self.component_registry = ComponentRegistry(self.zk_client)
        # We don't have any other component to initialize the global
        # registry in these tests, so we do it ourselves.
        COMPONENT_REGISTRY.create(self.zk_client)

    def waitForCache(self, cache, contents):
        paths = set(contents.keys())
        for _ in iterate_timeout(10, 'cache to sync'):
            cached_paths = cache._cached_paths.copy()
            cached_paths.discard(cache.root)
            object_paths = set(
                [x.path for x in cache._cached_objects.values()])
            if paths == cached_paths == object_paths:
                found = True
                for obj in cache._cached_objects.values():
                    if contents[obj.path] != obj.data:
                        found = False
                if found:
                    return

    def test_tree_cache(self):
        client = self.zk_client.client
        data = b'{}'
        client.create('/test', data)
        client.create('/test/foo', data)
        cache = SimpleTreeCache(self.zk_client, "/test")
        self.waitForCache(cache, {
            '/test/foo': {},
        })
        client.create('/test/bar', data)
        self.waitForCache(cache, {
            '/test/foo': {},
            '/test/bar': {},
        })
        client.set('/test/bar', b'{"value":1}')
        self.waitForCache(cache, {
            '/test/foo': {},
            '/test/bar': {'value': 1},
        })
        client.delete('/test/bar')
        self.waitForCache(cache, {
            '/test/foo': {},
        })

        # Simulate a change happening while the state was lost
        cache._cached_paths.add('/test/bar')
        cache._sessionListener(KazooState.LOST)
        cache._sessionListener(KazooState.CONNECTED)
        self.waitForCache(cache, {
            '/test/foo': {},
        })

        # Simulate a change happening while the state was suspendede
        cache._cached_paths.add('/test/bar')
        cache._sessionListener(KazooState.SUSPENDED)
        cache._sessionListener(KazooState.CONNECTED)
        self.waitForCache(cache, {
            '/test/foo': {},
        })

    def test_tree_cache_root(self):
        client = self.zk_client.client
        data = b'{}'
        client.create('/foo', data)
        cache = SimpleTreeCache(self.zk_client, "/")
        for _ in iterate_timeout(10, 'cache to sync'):
            cached_paths = cache._cached_paths.copy()
            cached_paths.discard(cache.root)
            object_paths = set(
                [x.path for x in cache._cached_objects.values()])
            if ('/foo' in cached_paths and
                '/foo' in object_paths):
                break

    def test_tree_cache_qsize_warning(self):
        with self.assertLogs('zuul.zk.ZooKeeper', level='DEBUG') as logs:
            cache = SimpleTreeCache(self.zk_client, "/test")
            cache._last_event_warning = 0
            cache._last_playback_warning = 0
            cache.qsize_warning_threshold = -1

            data = b'{}'
            client = self.zk_client.client
            client.create('/test/foo', data)
            self.waitForCache(cache, {
                '/test/foo': {},
            })

            found_event_warning = False
            found_playback_warning = False
            for line in logs.output:
                self.log.debug("Received %s", str(line))
                if 'Event queue size for cache' in str(line):
                    found_event_warning = True
                if 'Playback queue size for cache' in str(line):
                    found_playback_warning = True
            self.assertTrue(found_event_warning)
            self.assertTrue(found_playback_warning)
