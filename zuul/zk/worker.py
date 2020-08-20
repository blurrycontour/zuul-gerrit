# Copyright 2020 BMW Group
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, softwareite
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import logging
import threading
import time
from typing import Dict
from typing import Optional, List, Callable

from zuul.zk import ZooKeeper
from zuul.zk.cache import ZooKeeperBuildItem


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
        self._zk.watch_node_children(self.__watch_node, self._process_children)
        self.__thread.start()

    def stop(self) -> None:
        self.__running = False
        self.join()

    def join(self) -> None:
        self._zk.unwatch_node_children_completely(self.__watch_node)
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


class ZookeeperBuildJobWorker(ZookeeperWorker):
    def __init__(self, zk: ZooKeeper,
                 executor: Callable[[ZooKeeperBuildItem], None],
                 resume: Callable[[ZooKeeperBuildItem], None],
                 stop: Callable[[ZooKeeperBuildItem], None]):
        super().__init__(zk, zk.ZUUL_BUILDS_ROOT)
        self.log = logging.getLogger("zuul.lib.ZookeeperBuildJobWorker")
        self.__job_executor = executor
        self.__job_resume = resume
        self.__job_stop = stop
        self.__build_items = {}  # type: Dict[str, ZooKeeperBuildItem]

    def _process_children(self, children: Optional[List[str]]) -> None:
        items = list(self.__build_items.items())
        for node_path, build_item in items:
            self._zk.resumeBuildAttempt(build_item.lock, self.__job_resume)
            self._zk.cancelBuildAttempt(build_item.lock, self.__job_stop)
            if build_item.lock and not build_item.lock.is_aquired():
                del self.__build_items[node_path]

        try:
            next_item = self._zk.getNextJob()
            if next_item:
                self.__build_items[next_item.content['path']] = next_item
                try:
                    self.__job_executor(next_item)
                except Exception:
                    self.log.exception('Exception while running job')
                    # job.sendWorkException(
                    #     traceback.format_exc().encode('utf-8'))
        except Exception:
            self.log.exception('Exception while getting job')
