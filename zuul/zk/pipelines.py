# Copyright 2021 BMW Group
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

import contextlib
import json
import logging
import threading
import uuid
from urllib.parse import unquote_plus, quote_plus

from kazoo.exceptions import NoNodeError
from kazoo.recipe.cache import TreeCache

from zuul import model
from zuul.zk import ZooKeeperSimpleBase
from zuul.zk.exceptions import SyncTimeoutException


class PipelineCache(ZooKeeperSimpleBase):

    def __init__(self, client):
        super().__init__(client)
        self.root_path = "/zuul/pipelines"
        self.sync_root = f"{self.root_path}/_sync"
        self.kazoo_client.ensure_path(self.sync_root)
        self._sync_watches = {}
        self.tree_cache = TreeCache(self.kazoo_client, self.root_path)
        self.tree_cache.listen(self._onCacheEvent)
        self.tree_cache.listen_fault(self._onCacheError)

    def _onCacheEvent(self, event):
        if event.event_data is None:
            return
        if not event.event_data.path.startswith(f"{self.sync_root}/"):
            return
        with contextlib.suppress(KeyError):
            watch = self._sync_watches[event.event_data.path]
            watch.set()

    def _onCacheError(self, exception):
        self.log.exception(exception)

    def waitForSync(self, timeout=None):
        sync_path = f"{self.sync_root}/{uuid.uuid4().hex}"
        watch = self._sync_watches[sync_path] = threading.Event()
        try:
            self.kazoo_client.create(sync_path, b"", ephemeral=True)
            if not watch.wait(timeout):
                raise SyncTimeoutException("Timeout waiting for cache to sync")
        finally:
            with contextlib.suppress(KeyError):
                del self._sync_watches[sync_path]
            with contextlib.suppress(NoNodeError):
                self.kazoo_client.delete(sync_path)

    def start(self):
        self.tree_cache.start()

    def stop(self):
        self.tree_cache.close()


class PipelineStore(ZooKeeperSimpleBase):

    log = logging.getLogger("zuul.zk.pipelines.PipelineStore")

    def __init__(self, cache, tenant_name, pipeline_name):
        super().__init__(cache.client)
        self.cache = cache
        self._tree_cache = cache.tree_cache
        self.pipeline_root = f"{cache.root_path}/{tenant_name}/{pipeline_name}"
        self.queue_root = f"{self.pipeline_root}/queues"
        self.items_root = f"{self.pipeline_root}/items"
        self.kazoo_client.ensure_path(self.queue_root)
        self.kazoo_client.ensure_path(self.items_root)

    def queuePath(self, queue_identifier):
        return f"{self.queue_root}/{queue_identifier}"

    def queueItemPath(self, item_uuid):
        return f"{self.pipeline_root}/items/{item_uuid}"

    def buildSetPath(self, item_uuid, build_set_uuid):
        queue_item_root = self.queueItemPath(item_uuid)
        return f"{queue_item_root}/{build_set_uuid}"

    def buildPath(self, item_uuid, build_set_uuid, build_uuid):
        build_set_path = self.buildSetPath(item_uuid, build_set_uuid)
        return f"{build_set_path}/{build_uuid}"

    def _set_or_create(self, path, data):
        try:
            self.kazoo_client.set(path, data)
        except NoNodeError:
            self.kazoo_client.create(path, data, makepath=True)

    def saveState(self, pipeline):
        self.log.debug("Saving state for pipeline %s", pipeline)
        self.savePipelineState(pipeline)
        for queue in pipeline.queues:
            self.saveQueueState(queue)
            seen_items = []
            for item in queue.queue:
                seen_items.append(item.uuid)
                self.saveItemState(item)
                self.saveBuildSetState(item.current_build_set)
                for build in item.current_build_set.builds.values():
                    if not build:
                        continue
                    self.saveBuildState(build)
        # TODO: housekeeping - cleanup outdated queues

    def restoreState(self, pipeline):
        self.log.debug("Restoring state for pipeline %s", pipeline)
        self.cache.waitForSync(timeout=10)
        self._restorePipelineState(pipeline)
        self._restoreQueueStates(pipeline)

    def savePipelineState(self, pipeline):
        state = pipeline.toDict()
        self.log.debug(f"SWE> pipeline state: {state}")
        self.kazoo_client.set(self.pipeline_root,
                              json.dumps(state).encode("utf8"))

    def _restorePipelineState(self, pipeline):
        node_data = self._tree_cache.get_data(self.pipeline_root)
        if not (node_data and node_data.data):
            return
        state = json.loads(node_data.data)
        pipeline.updateFromDict(state)

    def saveQueueState(self, queue):
        state = queue.toDict()
        self.log.debug(f"SWE> saving queue state: {state}")
        data = json.dumps(state).encode("utf8")
        queue_path = self.queuePath(quote_plus(queue.id))
        self._set_or_create(queue_path, data)

    def _restoreQueueStates(self, pipeline):
        existing_queues = {q.id: q for q in pipeline.queues}
        self.log.debug(f"SWE> existing queues: {existing_queues}")
        pipeline.queues = []
        for qid, queue_state in self._getQueueStates(pipeline.name):
            self.log.debug(f"SWE> qid: {qid}")
            self.log.debug(f"SWE> qstate: {queue_state}")
            try:
                queue = existing_queues[qid]
            except KeyError:
                queue = model.ChangeQueue(pipeline)
            queue.updateFromDict(queue_state)
            self._restoreItemStates(queue)
            if queue.dynamic and not queue.queue:
                # Don't add empty dynamic queues. They will be cleaned up
                # by housekeeping later on.
                continue
            pipeline.queues.append(queue)

    def _getQueueStates(self, pipeline_name):
        # TODO: check if the order of the queues in the pipeline is important
        try:
            queue_ids = self._tree_cache.get_children(self.queue_root,
                                                      default=[])
        except NoNodeError:
            return
        for qid in queue_ids:
            # TODO: check if we can have some kind of checksum to know if we
            # need to update the object or not.
            self.log.debug(f"SWE> queue path: {qid}")
            node_data = self._tree_cache.get_data(self.queuePath(qid))
            yield unquote_plus(qid), json.loads(node_data.data)

    def saveItemState(self, item):
        path = self.queueItemPath(item.uuid)
        state = item.toDict()
        data = json.dumps(state).encode("utf8")
        self.log.debug(f"SWE> saving item state: {state}")
        self._set_or_create(path, data)

    def _restoreItemStates(self, queue):
        for item in queue.queue:
            node_data = self._tree_cache.get_data(
                self.queueItemPath(item.uuid))
            state = json.loads(node_data.data)
            item.updateFromDict(state)
            self._restoreBuildSetState(item.current_build_set)

    def cleanupPipeline(self, pipeline):
        # FIXME: this is just a hack to unconditionally cleanup orphaned
        # items. In the future we have to make sure that we also cleanup
        # all referenced build and node requests.
        valid_items = {i.uuid for i in pipeline.getAllItems()}
        all_items = self._tree_cache.get_children(self.items_root)
        items_to_clean = all_items - valid_items
        for item_uuid in items_to_clean:
            with contextlib.suppress(NoNodeError):
                self.kazoo_client.delete(self.queueItemPath(item_uuid),
                                         recursive=True)

    def saveBuildSetState(self, build_set):
        path = self.buildSetPath(build_set.item.uuid, build_set.uuid)
        state = build_set.toDict()
        self.log.debug(f"SWE> saving build set state: {state}")
        data = json.dumps(state).encode("utf8")
        self._set_or_create(path, data)

    def _restoreBuildSetState(self, build_set):
        self.log.debug(f"SWE> restoring state for build set {build_set.uuid}")
        node_data = self._tree_cache.get_data(
            self.buildSetPath(build_set.item.uuid, build_set.uuid))
        if node_data is None:
            return
        state = json.loads(node_data.data)
        self.log.debug(f"SWE> loading build set state: {state}")
        build_set.updateFromDict(state)
        existing_builds = {b.uuid: b for b in build_set.builds.values()}
        for build in build_set.builds.values():
            build_state = self._getBuildState(build_set, build.uuid)
            build.updateFromDict(build_state)

    def saveBuildState(self, build):
        path = self.buildPath(build.build_set.item.uuid, build.build_set.uuid,
                              build.uuid)
        state = build.toDict()
        self.log.debug(f"SWE> saving build state: {state}")
        data = json.dumps(state).encode("utf8")
        self._set_or_create(path, data)

    def _getBuildState(self, build_set, build_id):
        self.log.debug(f"SWE> loading build: {build_id}")
        node_data = self._tree_cache.get_data(
            self.buildPath(build_set.item.uuid, build_set.uuid, build_id))
        return json.loads(node_data.data)
