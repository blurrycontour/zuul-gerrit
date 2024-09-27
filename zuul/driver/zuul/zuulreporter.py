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

from zuul.lib.result_data import get_artifacts_from_result_data
from zuul.reporter import BaseReporter


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

    def addImageValidateEvent(self, image):
        tenant_name = self.pipeline.tenant.name
        sched = self.driver.sched
        project_hostname, project_name = \
            image.project_canonical_name.split('/', 1)
        event = self.driver.getImageBuildEvent(
            image.name, project_hostname, project_name, image.branch)
        self.log.info("Submitting image validate event for %s %s",
                      tenant_name, image.name)
        sched.trigger_events[tenant_name].put(event.trigger_name, event)

    def reportImageBuilt(self, item):
        sched = self.driver.sched

        for build in item.current_build_set.getBuilds():
            if not build.job.image_build_name:
                continue
            image_name = build.job.image_build_name
            image = self.pipeline.tenant.layout.images[image_name]
            for artifact in get_artifacts_from_result_data(
                    build.result_data,
                    logger=self.log):
                if metadata := artifact.get('metadata'):
                    if metadata.get('type') == 'zuul_image':
                        iba = sched.createImageBuildArtifact(
                            image, build, metadata['format'], artifact['url'],
                            self.image_validated)
                        sched.createImageUploads(iba)


def getSchema():
    zuul_reporter = {
        'image-built': bool,
        'image-validated': bool,
    }

    return zuul_reporter
