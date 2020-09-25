# Copyright 2020 BMW Group
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
from typing import Dict, Any, Union, ItemsView, TypeVar, Generic, Callable,\
    Optional, List

from kazoo.client import KazooClient
from kazoo.exceptions import BadVersionError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.cache import TreeCache
from kazoo.recipe.cache import TreeEvent

from zuul.zk.cache import ZooKeeperBuildItem, ZooKeeperCacheItem
from zuul.zk.exceptions import BadItemException

T = TypeVar('T', ZooKeeperCacheItem, ZooKeeperBuildItem)
L = Callable[[List[str], TreeEvent, Optional[T]], None]


def event_type_str(event: TreeEvent):
    """
    Helper function for debug messages translating TreeEvent type to a human
    readable character:

        A: NODE_ADDED
        U: NODE_UPDATED
        D: NODE_REMOVED

    :param event: TreeEvent
    :return: Human readable character representing the TreeEvent type.
    """
    if event.event_type == TreeEvent.NODE_ADDED:
        return 'A'
    elif event.event_type == TreeEvent.NODE_UPDATED:
        return 'U'
    elif event.event_type == TreeEvent.NODE_REMOVED:
        return 'D'
    return '?'


class ZooKeeperTreeCacheClient(Generic[T]):
    """
    Zookeeper tree cache client which automatically updates a generic sub-tree
    of watched ZNode.
    """
    def __init__(self, client: KazooClient, root: str,
                 multilevel: bool = False, listener: Optional[L] = None):
        class_name = self.__class__.__name__
        self.log = logging.getLogger('zuul.zk.%s' % class_name)
        self._client: KazooClient = client
        self._root: str = root
        self._tree_cache: Optional[TreeCache] = None
        self._cache: Dict[str, T] = {}
        self._multilevel: bool = multilevel
        self._listeners: List[L] = [listener] if listener else []

    def __str__(self):
        return "<ZooKeeperTreeCacheClient root=%s, hash=%s>" % (
            self._root, hex(hash(self)))

    def __getitem__(self, item: Union[str, List[str]]) -> Optional[T]:
        segments = self._getSegments(item) if isinstance(item, str) else item
        cache_key = self._getKey(segments)
        return self._cache.get(cache_key)

    def items(self) -> ItemsView[str, T]:
        return self._cache.items()

    def start(self) -> None:
        if self._tree_cache is not None:
            self.stop()

        self._tree_cache = TreeCache(self._client, self._root)
        self._tree_cache.listen_fault(self._treeCacheFaultListener)
        self._tree_cache.listen(self._treeCacheListener)
        self._tree_cache.start()

    def stop(self) -> None:
        if self._tree_cache is not None:
            self._tree_cache.close()
            self._tree_cache = None

    def registerListener(self, listener: L):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _getKey(self, segments: List[str]) -> str:
        relative = "/".join(segments) if self._multilevel else segments[0]
        return "%s/%s" % (self._root, relative)

    def _getSegments(self, path: str) -> List[str]:
        return (path[len(self._root) + 1:]
                if path.startswith(self._root) else path).split('/')

    def _getCachedStat(self, segments: List[str], cached: T) -> ZnodeStat:
        # Only first level props are relevant
        prop = 'stat' if self._multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        return getattr(cached, prop, None)

    def _setCachedStat(self, segments: List[str], cached: T,
                       stat: ZnodeStat) -> None:
        # Only first level props are relevant
        prop = 'stat' if self._multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        setattr(cached, prop, stat)

    def _setCachedValue(self, segments: List[str], cached: T,
                        value: Any) -> None:
        # Only first level props are relevant
        prop = 'content' if self._multilevel or len(segments) == 1\
            else segments[1]
        setattr(cached, prop, value)

    def _createCachedValue(self, path: str,
                           content: Union[Dict[str, Any], bool],
                           stat: ZnodeStat) -> T:
        """
        Create a new cache item from a "TreeEvent" of the type
        "TreeEvent.NODE_ADDED". This needs to be overridden in order to create
        a proper cache instance.

        :param path: Path to the ZNode
        :param content: Content of the node
        :param stat: ZnodeStat of the new ZNode
        :return: New cache item
        """
        raise Exception("Not implemented!")

    def _deleteCachedValue(self, segments: List[str]) -> None:
        if self._multilevel or len(segments) == 1:
            try:
                del self._cache[self._getKey(segments)]
            except KeyError:
                pass
        else:
            try:
                cached = self[segments]
                prop = segments[1]  # Only first level props are relevant
                value = getattr(cached, prop, False)
                setattr(cached, prop, False if type(value) == bool else None)
            except KeyError:
                pass

    def _treeCacheListener(self, event: TreeEvent) -> None:
        try:
            if hasattr(event.event_data, 'path'):
                path = event.event_data.path
                if path == self._root:
                    return  # Ignore root node
            else:
                return  # Ignore events without path

            if event.event_type not in (TreeEvent.NODE_ADDED,
                                        TreeEvent.NODE_UPDATED,
                                        TreeEvent.NODE_REMOVED):
                return  # Ignore non node events

            if not event.event_data.path.startswith(self._root):
                return  # Ignore events outside root path

            segments = self._getSegments(event.event_data.path)

            # Ignore lock nodes: last segment = /[0-9a-f]{32}__lock__\d{10}/
            if "_lock_" in segments[-1]:
                return

            cached = self[segments]

            if event.event_data.data and event.event_type in (
                    TreeEvent.NODE_ADDED, TreeEvent.NODE_UPDATED):

                # Perform an in-place update of the already cached request
                data_value = event.event_data.data
                try:
                    data = json.loads(data_value.decode(encoding='UTF-8'))
                except Exception:
                    data = True

                if cached:
                    cached_stat = self._getCachedStat(segments, cached)
                    if cached_stat and event.event_data.stat\
                            .version <= cached_stat.version:
                        return  # Don't update to older data
                    self._setCachedValue(segments, cached, data)
                    self._setCachedStat(segments, cached,
                                        event.event_data.stat)
                    cached.stat = event.event_data.stat
                elif len(segments) == 1:  # Only create for top level
                    try:
                        cached = self._createCachedValue(
                            event.event_data.path, data, event.event_data.stat)
                        self._cache[self._getKey(segments)] = cached
                    except BadItemException:
                        # Raising this exception tells us that an invalid node
                        # was added and should be cleaned up. This can happen,
                        # e.g., when a node gets deleted and then the lock
                        # on that node is accessed - which creates an empty
                        # node under the same path.
                        try:
                            self._client.delete(
                                path,
                                version=event.event_data.stat.version,
                                recursive=True)
                        except BadVersionError:
                            self.log.warning("Bad item %s cannot be removed",
                                             path)
                            pass

            elif event.event_type == TreeEvent.NODE_REMOVED:
                self._deleteCachedValue(segments)
                cached = None

            for listener in self._listeners:
                try:
                    listener(segments, event, cached)
                except Exception:
                    self.log.exception("Event %s for %s failed!",
                                       event, segments)

        except Exception:
            self.log.exception("Cache update exception for event: %s", event)

    def _treeCacheFaultListener(self, e: Exception):
        self.log.exception(e)
