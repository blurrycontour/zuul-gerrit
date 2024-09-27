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
from zuul.model import ImageBuildArtifact, ImageUpload


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
        keys = list(self.builds_by_image_name[image_canonical_name])
        arts = [self._cached_objects[key] for key in keys]
        # Sort in a stable order, primarily by timestamp, then format
        # for identical timestamps.
        arts = sorted(arts, key=lambda x: x.format)
        arts = sorted(arts, key=lambda x: x.timestamp)
        return arts


class ImageUploadRegistry(LockableZKObjectCache):

    def __init__(self, zk_client, upload_added_event=None):
        super().__init__(
            zk_client,
            None,
            root=ImageUpload.ROOT,
            items_path=ImageUpload.UPLOADS_PATH,
            locks_path=ImageUpload.LOCKS_PATH,
            zkobject_class=ImageUpload,
        )
        self.uploads_by_image_name = collections.defaultdict(set)
        self.upload_added_event = upload_added_event

    def postCacheHook(self, event, data, stat, key, obj):
        super().postCacheHook(event, data, stat, key, obj)
        if obj is None:
            return
        exists = key in self._cached_objects
        uploads = self.uploads_by_image_name[obj.canonical_name]
        if exists:
            uploads.add(key)
            if self.upload_added_event:
                self.upload_added_event()
        else:
            uploads.discard(key)

    def getUploadsForImage(self, image_canonical_name):
        keys = list(self.uploads_by_image_name[image_canonical_name])
        uploads = [self._cached_objects[key] for key in keys]
        uploads = sorted(uploads, key=lambda x: x.timestamp)
        return uploads
