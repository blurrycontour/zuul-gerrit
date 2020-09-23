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
import threading
import time
from typing import Optional, List

from zuul.zk import ZooKeeper


class ZookeeperWorker:
    """A thread that observes zookeeper node for changes"""

    def __init__(self, zk: ZooKeeper, watch_node: str):
        class_name = self.__class__.__name__
        self.log = logging.getLogger('zuul.zk.%s' % class_name)
        self.__running = True
        self.__lock = threading.Lock()
        self._zk = zk
        self.__watch_node = watch_node

        self.__thread = threading.Thread(target=self.__run,
                                         name='%sThread' % class_name)
        self.__thread.daemon = True

    def start(self) -> None:
        self._zk.client.watch_node_children(self.__watch_node,
                                            self._process_children)
        self.__thread.start()

    def stop(self) -> None:
        self.__running = False
        self.join()

    def join(self) -> None:
        self._zk.client.unwatch_node_children_completely(self.__watch_node)
        self.__thread.join()

    def __run(self):
        """
        This provides an additional check for new children nodes in zookeeper
        in case an watch event gets lost.
        """
        while self.__running:
            self._process_children(None)
            time.sleep(1)

    def _process_children(self, children: Optional[List[str]]) -> None:
        """
        Children change processor.
        :param children: Changed children or `None` in case of call from looper
        """
        pass
