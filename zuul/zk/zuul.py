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


class ZooKeeperZuulBase(object):
    ZUUL_CONFIG_ROOT = "/zuul"
    # Node content max size: keep ~100kB as a reserve form the 1MB limit
    ZUUL_CONFIG_MAX_SIZE = 1024 * 1024 - 100 * 1024

    log = logging.getLogger("zuul.zk.zuul.ZooKeeperZuul")

    def _getZuulNodePath(self, *args: str) -> str:
        return "/".join(filter(lambda s: s is not None and s != '',
                               [self.ZUUL_CONFIG_ROOT] + list(args)))
