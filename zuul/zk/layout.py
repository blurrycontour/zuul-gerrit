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
from functools import total_ordering
from uuid import uuid4

from kazoo.exceptions import NoNodeError

from zuul.zk import ZooKeeperBase


@total_ordering
class LayoutState:
    def __init__(self, tenant_name, hostname, last_reconfigured, uuid=None,
                 ltime=-1):
        self.uuid = uuid or uuid4().hex
        self.ltime = -1
        self.tenant_name = tenant_name
        self.hostname = hostname
        self.last_reconfigured = last_reconfigured

    def to_dict(self):
        return {
            "tenant_name": self.tenant_name,
            "hostname": self.hostname,
            "last_reconfigured": self.last_reconfigured,
            "uuid": self.uuid,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["tenant_name"],
            data["hostname"],
            data["last_reconfigured"],
            data.get("uuid"),
            data.get("ltime", -1),
        )

    def __eq__(self, other):
        if not isinstance(other, LayoutState):
            return False
        return self.uuid == other.uuid

    def __gt__(self, other):
        if not isinstance(other, LayoutState):
            return False
        return self.ltime > other.ltime

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} {self.tenant_name}: "
            f"ltime={self.ltime}, "
            f"hostname={self.hostname}, "
            f"last_reconfigured={self.last_reconfigured}>"
        )


class LayoutStateStore(ZooKeeperBase, MutableMapping):

    layout_root = "/zuul/layout"

    def __getitem__(self, tenant_name):
        try:
            data, zstat = self.kazoo_client.get(
                f"{self.layout_root}/{tenant_name}")
        except NoNodeError:
            raise KeyError(tenant_name)

        return LayoutState.from_dict({
            "ltime": zstat.last_modified_transaction_id,
            **json.loads(data)
        })

    def __setitem__(self, tenant_name, state):
        path = f"{self.layout_root}/{tenant_name}"
        self.kazoo_client.ensure_path(path)
        data = json.dumps(state.to_dict()).encode("utf-8")
        zstat = self.kazoo_client.set(path, data)
        # Set correct ltime of the layout in Zookeeper
        state.ltime = zstat.last_modified_transaction_id

    def __delitem__(self, tenant_name):
        try:
            self.kazoo_client.delete(f"{self.layout_root}/{tenant_name}")
        except NoNodeError:
            raise KeyError(tenant_name)

    def __iter__(self):
        try:
            tenant_names = self.kazoo_client.get_children(self.layout_root)
        except NoNodeError:
            return
        yield from tenant_names

    def __len__(self):
        zstat = self.kazoo_client.exists(self.layout_root)
        if zstat is None:
            return 0
        return zstat.children_count
