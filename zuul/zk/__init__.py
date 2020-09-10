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
from typing import Optional

from kazoo.client import KazooClient

from zuul.zk.base import ZooKeeperClient
from zuul.zk.nodepool import ZooKeeperNodepool


class ZooKeeper(object):
    """
    Class implementing the ZooKeeper interface.

    This class uses the facade design pattern to keep common interaction
    with the ZooKeeper API simple and consistent for the caller, and
    limits coupling between objects. It allows for more complex interactions
    by providing direct access to the client connection when needed (though
    that is discouraged). It also provides for a convenient entry point for
    testing only ZooKeeper interactions.
    """

    def __init__(self, enable_cache: bool=True):
        """
        Initialize the ZooKeeper object.

        :param bool enable_cache: When True, enables caching of ZooKeeper
            objects (e.g., HoldRequests).
        """
        self.client = ZooKeeperClient()
        self.nodepool = ZooKeeperNodepool(self.client,
                                          enable_cache=enable_cache)

    @property
    def kazoo_client(self) -> Optional[KazooClient]:
        return self.client.client

    def connect(self, hosts: str, read_only: bool = False,
                timeout: float = 10.0,
                tls_cert: Optional[str] = None, tls_key: Optional[str] = None,
                tls_ca: Optional[str] = None):
        self.client.connect(hosts, read_only, timeout, tls_cert, tls_key,
                            tls_ca)

    def disconnect(self):
        self.client.disconnect()
