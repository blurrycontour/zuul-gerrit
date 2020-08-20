import json
import logging
from copy import deepcopy
from typing import Dict, Any, Union, ItemsView, TYPE_CHECKING
from typing import Optional, List

from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.cache import TreeCache
from kazoo.recipe.cache import TreeEvent

if TYPE_CHECKING:
    from zuul.zk import ZooKeeper
from zuul.zk.cache import ZooKeeperCacheItem


class ZooKeeperTreeCacheClient:
    def __init__(self, zk: 'ZooKeeper', root: str, multilevel: bool=False):
        class_name = self.__class__.__name__
        self.log = logging.getLogger('zuul.zk.%s' % class_name)
        self._zk = zk  # type: ZooKeeper
        self.__root = root  # type: str
        self.__tree_cache = None  # type: Optional[TreeCache]
        self._cache = {}  # type: Dict[str, ZooKeeperCacheItem]
        self.__multilevel = multilevel

    def __getitem__(self, item: Union[str, List[str]])\
            -> Optional[ZooKeeperCacheItem]:
        segments = self.__get_segments(item) if isinstance(item, str) else item
        cache_key = self.__get_key(segments)
        return self._cache.get(cache_key)

    def items(self) -> ItemsView[str, ZooKeeperCacheItem]:
        return self._cache.items()

    def start(self) -> None:
        if self.__tree_cache is not None:
            self.stop()

        self.__tree_cache = TreeCache(self._zk.client, self.__root)
        self.__tree_cache.listen_fault(self._tree_cache_fault_listener)
        self.__tree_cache.listen(self.__tree_cache_listener)
        self.__tree_cache.start()

    def stop(self) -> None:
        if self.__tree_cache is not None:
            self.__tree_cache.close()
            self.__tree_cache = None

    def __get_key(self, segments: List[str]) -> str:
        return "/".join(segments) if self.__multilevel else segments[0]

    def __get_segments(self, path: str) -> List[str]:
        return (path[len(self.__root) + 1:]
                if path.startswith(self.__root) else path).split('/')

    def __get_cached_stat(self, segments: List[str],
                          cached: ZooKeeperCacheItem) -> ZnodeStat:
        # Only first level props are relevant
        prop = 'stat' if self.__multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        return getattr(cached, prop, None)

    def __set_cached_stat(self, segments: List[str],
                          cached: ZooKeeperCacheItem,
                          stat: ZnodeStat) -> None:
        # Only first level props are relevant
        prop = 'stat' if self.__multilevel or len(segments) == 1\
            else '%s_stat' % segments[1]
        setattr(cached, prop, stat)

    def __set_cached_value(self, segments: List[str],
                           cached: ZooKeeperCacheItem,
                           value: Any) -> None:
        # Only first level props are relevant
        prop = 'content' if self.__multilevel or len(segments) == 1\
            else segments[1]
        setattr(cached, prop, value)

    def __delete_cached_value(self, segments: List[str])\
            -> None:
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
            cached = self[segments]
            previous = deepcopy(cached) if cached else None

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
                    cached = ZooKeeperCacheItem(data, event.event_data.stat)
                    self._cache[self.__get_key(segments)] = cached

            elif event.event_type == TreeEvent.NODE_REMOVED:
                self.__delete_cached_value(segments)
                cached = None

            self._tree_cache_listener(segments, event, previous, cached)

        except Exception:
            self.log.exception("Cache update exception for event: %s", event)

    def _tree_cache_listener(self, segments: List[str], event: TreeEvent,
                             old: Optional[ZooKeeperCacheItem],
                             new: Optional[ZooKeeperCacheItem]) -> None:
        pass

    def _tree_cache_fault_listener(self, e: Exception):
        self.log.exception(e)
