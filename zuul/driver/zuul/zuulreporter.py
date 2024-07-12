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

import logging
from uuid import uuid4

from zuul.lib.result_data import get_artifacts_from_result_data
from zuul.reporter import BaseReporter
from zuul.model import ImageBuildArtifact


class ZuulReporter(BaseReporter):
    def __init__(self, driver, connection, pipeline, config):
        super().__init__(driver, connection, config)
        self.log = logging.getLogger('zuul.reporter')
        self.pipeline = pipeline
        self.image_built = config.get('image-built', False)
        self.image_validated = config.get('image-validated', False)

    def report(self, item, phase1=True, phase2=True):
        if not phase2:
            return
        if self.image_built:
            self.reportImageBuilt(item)

    def reportImageBuilt(self, item):
        sched = self.driver.sched

        for build in item.current_build_set.getBuilds():
            for artifact in get_artifacts_from_result_data(
                    build.result_data,
                    logger=self.log):
                if metadata := artifact.get('metadata'):
                    if metadata.get('type') == 'zuul_image':
                        image_name = metadata['image_name']
                        fmt = metadata['format']
                        image = self.pipeline.tenant.layout.images[
                            image_name]
                        uuid = uuid4().hex
                        self.log.info(
                            "Storing image build artifact metadata: "
                            "uuid: %s name: %s format: %s build: %s url: %s",
                            uuid, image.canonical_name, fmt, build.uuid,
                            artifact['url'])
                        with sched.createZKContext(None, self.log) as ctx:
                            ImageBuildArtifact.new(
                                ctx,
                                uuid=uuid,
                                canonical_name=image.canonical_name,
                                build_uuid=build.uuid,
                                format=fmt,
                                url=artifact['url'],
                                timestamp=build.end_time,
                                validated=self.image_validated,
                            )


def getSchema():
    zuul_reporter = {
        'image-built': bool,
        'image-validated': bool,
    }

    return zuul_reporter
