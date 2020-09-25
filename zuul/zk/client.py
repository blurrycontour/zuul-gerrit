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
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.cache import TreeCache
from kazoo.recipe.cache import TreeEvent

from zuul.zk.cache import ZooKeeperBuildItem, ZooKeeperCacheItem

T = TypeVar('T', ZooKeeperCacheItem, ZooKeeperBuildItem)
L = Callable[[List[str], TreeEvent, Optional[T]], None]


def event_type_str(event: TreeEvent):
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
        self.__client: KazooClient = client
        self.__root: str = root
        self.__tree_cache: Optional[TreeCache] = None
        self._cache: Dict[str, T] = {}
        self.__multilevel: bool = multilevel
        self.__listeners: List[L] = [listener] if listener else []

    def __str__(self):
        return "<ZooKeeperTreeCacheClient root=%s, hash=%s>" % (
            self.__root, hex(hash(self)))

    def __getitem__(self, item: Union[str, List[str]]) -> Optional[T]:
        segments = self.__get_segments(item) if isinstance(item, str) else item
        cache_key = self.__get_key(segments)
        return self._cache.get(cache_key)

    def items(self) -> ItemsView[str, T]:
        return self._cache.items()

    def start(self) -> None:
        if self.__tree_cache is not None:
            self.stop()

        self.__tree_cache = TreeCache(self.__client, self.__root)
        self.__tree_cache.listen_fault(self._tree_cache_fault_listener)
        self.__tree_cache.listen(self.__tree_cache_listener)
        self.__tree_cache.start()

    def stop(self) -> None:
        if self.__tree_cache is not None:
            self.__tree_cache.close()
            self.__tree_cache = None

    def register_listener(self, listener: L):
        if listener not in self.__listeners:
            self.__listeners.append(listener)

    def __get_key(self, segments: List[str]) -> str:
        relative = "/".join(segments) if self.__multilevel else segments[0]
        return "%s/%s" % (self.__root, relative)

    def __get_segments(self, path: str) -> List[str]:
        return (path[len(self.__root) + 1:]
                if path.startswith(self.__root) else path).split('/')

    def __get_cached_stat(self, segments: List[str], cached: T) -> ZnodeStat:
        # Only first level props are relevant
        prop = 'stat' if self.__multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        return getattr(cached, prop, None)

    def __set_cached_stat(self, segments: List[str], cached: T,
                          stat: ZnodeStat) -> None:
        # Only first level props are relevant
        prop = 'stat' if self.__multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        setattr(cached, prop, stat)

    def __set_cached_value(self, segments: List[str], cached: T,
                           value: Any) -> None:
        # Only first level props are relevant
        prop = 'content' if self.__multilevel or len(segments) == 1\
            else segments[1]
        setattr(cached, prop, value)

    def _create_cached_value(self, path: str, content: Dict[str, Any],
                             stat: ZnodeStat) -> T:
        raise Exception("Not implemented!")

    def __delete_cached_value(self, segments: List[str]) -> None:
        if self.__multilevel or len(segments) == 1:
            try:
                del self._cache[self.__get_key(segments)]
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

    def __tree_cache_listener(self, event: TreeEvent) -> None:
        try:
            if hasattr(event.event_data, 'path'):
                path = event.event_data.path
                if path == self.__root:
                    return  # Ignore root node

            if event.event_type not in (TreeEvent.NODE_ADDED,
                                        TreeEvent.NODE_UPDATED,
                                        TreeEvent.NODE_REMOVED):
                return  # Ignore non node events

            if not event.event_data.path.startswith(self.__root):
                return  # Ignore events outside root path

            segments = self.__get_segments(event.event_data.path)

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
                    cached_stat = self.__get_cached_stat(segments, cached)
                    if cached_stat and event.event_data.stat\
                            .version <= cached_stat.version:
                        return  # Don't update to older data
                    self.__set_cached_value(segments, cached, data)
                    self.__set_cached_stat(segments, cached,
                                           event.event_data.stat)
                    cached.stat = event.event_data.stat
                elif len(segments) == 1:  # Only create for top level
                    cached = self._create_cached_value(
                        event.event_data.path, data, event.event_data.stat)
                    self._cache[self.__get_key(segments)] = cached

            elif event.event_type == TreeEvent.NODE_REMOVED:
                self.__delete_cached_value(segments)
                cached = None

            for listener in self.__listeners:
                listener(segments, event, cached)

        except Exception:
            self.log.exception("Cache update exception for event: %s", event)

    def _tree_cache_fault_listener(self, e: Exception):
        self.log.exception(e)
