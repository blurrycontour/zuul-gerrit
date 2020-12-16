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
from collections.abc import MutableMapping
from functools import partial, total_ordering
from uuid import uuid4
from typing import Any, Callable, Dict, Iterator, List, Optional, Set

from kazoo.exceptions import NoNodeError
from kazoo.protocol.states import (
    EventType,
    KazooState,
    WatchedEvent,
    ZnodeStat,
)

from zuul.zk import ZooKeeperBase, ZooKeeperClient


@total_ordering
class LayoutState:
    def __init__(
        self,
        tenant_name: str,
        hostname: str,
        last_reconfigured: int,
        uuid: Optional[str] = None,
        ltime: int = -1,
    ):
        self.uuid = uuid or uuid4().hex
        self.ltime = -1
        self.tenant_name = tenant_name
        self.hostname = hostname
        self.last_reconfigured = last_reconfigured

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_name": self.tenant_name,
            "hostname": self.hostname,
            "last_reconfigured": self.last_reconfigured,
            "uuid": self.uuid,
        }

    @classmethod
    def from_dict(cls, data) -> "LayoutState":
        return cls(
            data["tenant_name"],
            data["hostname"],
            data["last_reconfigured"],
            data.get("uuid"),
            data.get("ltime", -1),
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, LayoutState):
            return False
        return self.uuid == other.uuid

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, LayoutState):
            return False
        return self.ltime > other.ltime

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} {self.tenant_name}: "
            f"ltime={self.ltime}, "
            f"hostname={self.hostname}, "
            f"last_reconfigured={self.last_reconfigured}>"
        )


class LayoutStateStore(ZooKeeperBase, MutableMapping):

    layout_root = "/zuul/layout"

    # Make instance hashable in order to allow hashing of _on_state_change
    # callback with Python <3.8
    __hash__ = object.__hash__

    def __init__(
        self,
        client: ZooKeeperClient,
        callback: Callable[[LayoutState], Any],
    ):
        super().__init__(client)
        self._watched_tenants: Set[str] = set()
        self.callback = callback
        self.kazoo_client.ensure_path(self.layout_root)
        self.kazoo_client.add_listener(self._on_state_change)

    def _on_state_change(self, state: KazooState) -> None:
        if state == KazooState.LOST:
            # Data watches are no longer valid and will be re-created by
            # the child watch which survives session loss.
            self._watched_tenants.clear()

    def watch(self) -> None:
        self.kazoo_client.ChildrenWatch(self.layout_root, self._layout_watch)

    def _layout_watch(
        self,
        tenant_list: List[str],
        event: Optional[WatchedEvent] = None,
    ) -> None:
        new_tenants = set(tenant_list) - self._watched_tenants
        for tenant_name in new_tenants:
            self.kazoo_client.DataWatch(
                f"{self.layout_root}/{tenant_name}",
                partial(self._tenant_data_watch, tenant_name),
            )
            self._watched_tenants.add(tenant_name)

    def _tenant_data_watch(
        self,
        tenant_name: str,
        data: bytes,
        zstat: ZnodeStat,
        event: WatchedEvent,
    ) -> bool:
        if event and event.type == EventType.DELETED:
            self._watched_tenants.discard(tenant_name)
            return False
        if data:
            state = LayoutState.from_dict(
                {
                    "ltime": zstat.last_modified_transaction_id,
                    **json.loads(data),
                }
            )
            self.callback(state)
        return True

    def __getitem__(self, tenant_name: str) -> LayoutState:
        try:
            data, zstat = self.kazoo_client.get(
                f"{self.layout_root}/{tenant_name}"
            )
        except NoNodeError:
            raise KeyError(tenant_name)
        return LayoutState.from_dict(
            {"ltime": zstat.last_modified_transaction_id, **json.loads(data)}
        )

    def __setitem__(self, tenant_name: str, state: LayoutState) -> None:
        path = f"{self.layout_root}/{tenant_name}"
        self.kazoo_client.ensure_path(path)
        data = json.dumps(state.to_dict()).encode("utf-8")
        zstat = self.kazoo_client.set(path, data)
        # Set correct ltime of the layout in Zookeeper
        state.ltime = zstat.last_modified_transaction_id

    def __delitem__(self, tenant_name: str) -> None:
        try:
            self.kazoo_client.delete(f"{self.layout_root}/{tenant_name}")
        except NoNodeError:
            raise KeyError(tenant_name)

    def __iter__(self) -> Iterator[str]:
        try:
            tenant_names = self.kazoo_client.get_children(self.layout_root)
        except NoNodeError:
            return
        yield from tenant_names

    def __len__(self) -> int:
        zstat = self.kazoo_client.exists(self.layout_root)
        if zstat is None:
            return 0
        return zstat.children_count
