# Copyright 2024 Acme Gating, LLC
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

import collections

from zuul.zk.launcher import LockableZKObjectCache
from zuul.model import ImageBuildArtifact


class ImageBuildRegistry(LockableZKObjectCache):

    def __init__(self, zk_client):
        super().__init__(
            zk_client,
            None,
            root=ImageBuildArtifact.ROOT,
            items_path=ImageBuildArtifact.IMAGES_PATH,
            locks_path=ImageBuildArtifact.LOCKS_PATH,
            zkobject_class=ImageBuildArtifact,
        )
        self.builds_by_image_name = collections.defaultdict(set)

    def postCacheHook(self, event, data, stat, key, obj):
        super().postCacheHook(event, data, stat, key, obj)
        if obj is None:
            return
        exists = key in self._cached_objects
        builds = self.builds_by_image_name[obj.canonical_name]
        if exists:
            builds.add(key)
        else:
            builds.discard(key)

    def getArtifactsForImage(self, image_canonical_name):
        for key in list(self.builds_by_image_name[image_canonical_name]):
            yield self._cached_objects[key]
