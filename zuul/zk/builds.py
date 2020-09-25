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

import logging
from typing import Optional, Dict, Any, Union

from kazoo.client import KazooClient
from kazoo.protocol.states import ZnodeStat

from zuul.lib.logutil import get_annotated_logger
from zuul.zk.cache import ZooKeeperBuildItem
from zuul.zk.client import ZooKeeperTreeCacheClient, L
from zuul.zk.exceptions import BadItemException
from zuul.zk.work import ZooKeeperWorkBase


class ZooKeeperBuildTreeCacheClient(
        ZooKeeperTreeCacheClient[ZooKeeperBuildItem]):
    """
    Zookeeper build tree cache client watching the "/zuul/builds" tree.
    """
    _work_item_class = ZooKeeperBuildItem

    def __init__(self, client: KazooClient, zone: Optional[str] = None,
                 multilevel: bool = False,
                 listener: Optional[L] = None):
        root = "%s/%s" % (ZooKeeperBuilds.ROOT, zone) \
            if zone else ZooKeeperBuilds.ROOT
        super().__init__(client, root, multilevel, listener)

    def _createCachedValue(self, path: str,
                           content: Union[Dict[str, Any], bool],
                           stat: ZnodeStat) -> ZooKeeperBuildItem:
        # A valid build item must contain a non-empty dictionary
        if not content or isinstance(content, bool):
            raise BadItemException()
        return ZooKeeperBuildItem(path, content, stat)


class ZooKeeperBuilds(
        ZooKeeperWorkBase[ZooKeeperBuildTreeCacheClient, ZooKeeperBuildItem]):
    """
    Build relevant methods for ZooKeeper
    """
    ROOT = "/zuul/builds"

    log = logging.getLogger("zuul.zk.builds.ZooKeeperBuilds")
    _item_class = ZooKeeperBuildItem

    def _getAnnotatedLogger(self, item: Union[None, str, ZooKeeperBuildItem]):
        uuid = item.content['uuid'] \
            if item and isinstance(item, ZooKeeperBuildItem) else item
        return get_annotated_logger(self.log, None, build=uuid) \
            if uuid else self.log

    def _createTreeCacheClient(self, zone: str)\
            -> ZooKeeperBuildTreeCacheClient:
        return ZooKeeperBuildTreeCacheClient(self.kazoo_client, zone)
