# Copyright 2021 BMW Group
# Copyright 2021 Acme Gating, LLC
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
import logging
from urllib.parse import quote_plus, unquote

from kazoo.exceptions import BadVersionError, NoNodeError

from zuul.lib.logutil import get_annotated_logger
from zuul.model import PipelineSemaphoreReleaseEvent
from zuul.zk import ZooKeeperSimpleBase
from zuul.zk.components import COMPONENT_REGISTRY


def holdersFromData(data):
    if not data:
        return []
    return json.loads(data.decode("utf8"))


def holdersToData(holders):
    return json.dumps(holders, sort_keys=True).encode("utf8")


class SemaphoreHandler(ZooKeeperSimpleBase):
    log = logging.getLogger("zuul.zk.SemaphoreHandler")

    semaphore_root = "/zuul/semaphores"

    def __init__(self, client, statsd, tenant_name, layout):
        super().__init__(client)
        self.layout = layout
        self.statsd = statsd
        self.tenant_name = tenant_name
        self.tenant_root = f"{self.semaphore_root}/{tenant_name}"

    def _emitStats(self, semaphore_path, num_holders):
        if self.statsd is None:
            return
        try:
            semaphore_quoted = semaphore_path.split('/')[-1]
            semaphore_name = unquote(semaphore_quoted)
            # statsd safe key:
            semaphore_key = semaphore_name.replace('.', '_').replace('/', '_')
            key = (f'zuul.tenant.{self.tenant_name}'
                   f'.semaphore.{semaphore_key}')
            self.statsd.gauge(f'{key}.holders', num_holders)
        except Exception:
            self.log.exception("Unable to send semaphore stats:")

    def acquire(self, item, job, request_resources):
        if not job.semaphores:
            return True

        log = get_annotated_logger(self.log, item.event)
        all_acquired = True
        for semaphore in job.semaphores:
            if not self._acquire_one(log, item, job, request_resources,
                                     semaphore):
                all_acquired = False
                break
        if not all_acquired:
            # Since we know we have less than all the required
            # semaphores, set quiet=True so we don't log an inability
            # to release them.
            self.release(None, item, job, quiet=True)
            return False
        return True

    def _acquire_one(self, log, item, job, request_resources, semaphore):
        if semaphore.resources_first and request_resources:
            # We're currently in the resource request phase and want to get the
            # resources before locking. So we don't need to do anything here.
            return True
        else:
            # As a safety net we want to acuire the semaphore at least in the
            # run phase so don't filter this here as re-acuiring the semaphore
            # is not a problem here if it has been already acquired before in
            # the resources phase.
            pass

        semaphore_key = quote_plus(semaphore.name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        semaphore_handle = {
            "buildset_path": item.current_build_set.getPath(),
            "job_name": job.name,
        }
        legacy_handle = f"{item.uuid}-{job.name}"

        self.kazoo_client.ensure_path(semaphore_path)
        semaphore_holders, zstat = self.getHolders(semaphore_path)

        if (semaphore_handle in semaphore_holders
                or legacy_handle in semaphore_holders):
            return True

        # semaphore is there, check max
        while len(semaphore_holders) < self._max_count(semaphore.name):
            # MODEL_API: >1
            if COMPONENT_REGISTRY.model_api > 1:
                semaphore_holders.append(semaphore_handle)
            else:
                semaphore_holders.append(legacy_handle)

            try:
                self.kazoo_client.set(semaphore_path,
                                      holdersToData(semaphore_holders),
                                      version=zstat.version)
            except BadVersionError:
                log.debug(
                    "Retrying semaphore %s acquire due to concurrent update",
                    semaphore.name)
                semaphore_holders, zstat = self.getHolders(semaphore_path)
                continue

            log.info("Semaphore %s acquired: job %s, item %s",
                     semaphore.name, job.name, item)

            self._emitStats(semaphore_path, len(semaphore_holders))
            return True

        return False

    def getHolders(self, semaphore_path):
        data, zstat = self.kazoo_client.get(semaphore_path)
        return holdersFromData(data), zstat

    def getSemaphores(self):
        try:
            return self.kazoo_client.get_children(self.tenant_root)
        except NoNodeError:
            return []

    def _release(self, log, semaphore_path, semaphore_handle, quiet,
                 legacy_handle=None):
        while True:
            try:
                semaphore_holders, zstat = self.getHolders(semaphore_path)
                try:
                    semaphore_holders.remove(semaphore_handle)
                except ValueError:
                    if legacy_handle is None:
                        raise
                    semaphore_holders.remove(legacy_handle)
            except (ValueError, NoNodeError):
                if not quiet:
                    log.error("Semaphore %s can not be released for %s "
                              "because the semaphore is not held",
                              semaphore_path, semaphore_handle)
                break

            try:
                self.kazoo_client.set(semaphore_path,
                                      holdersToData(semaphore_holders),
                                      zstat.version)
            except BadVersionError:
                log.debug(
                    "Retrying semaphore %s release due to concurrent update",
                    semaphore_path)
                continue

            log.info("Semaphore %s released for %s",
                     semaphore_path, semaphore_handle)
            self._emitStats(semaphore_path, len(semaphore_holders))
            break

    def release(self, sched, item, job, quiet=False):
        if not job.semaphores:
            return

        log = get_annotated_logger(self.log, item.event)

        for semaphore in job.semaphores:
            self._release_one(log, item, job, semaphore, quiet)

        # If a scheduler has been provided (which it is except in the
        # case of a rollback from acquire in this class), broadcast an
        # event to trigger pipeline runs.
        if sched is None:
            return
        for pipeline_name in self.layout.pipelines.keys():
            event = PipelineSemaphoreReleaseEvent()
            sched.pipeline_management_events[
                self.tenant_name][pipeline_name].put(
                    event, needs_result=False)

    def _release_one(self, log, item, job, semaphore, quiet):
        semaphore_key = quote_plus(semaphore.name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        semaphore_handle = {
            "buildset_path": item.current_build_set.getPath(),
            "job_name": job.name,
        }
        legacy_handle = f"{item.uuid}-{job.name}"
        self._release(log, semaphore_path, semaphore_handle, quiet,
                      legacy_handle)

    def semaphoreHolders(self, semaphore_name):
        semaphore_key = quote_plus(semaphore_name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        try:
            holders, _ = self.getHolders(semaphore_path)
        except NoNodeError:
            holders = []
        return holders

    def _max_count(self, semaphore_name: str) -> int:
        semaphore = self.layout.semaphores.get(semaphore_name)
        return 1 if semaphore is None else semaphore.max

    def cleanupLeaks(self):
        # MODEL_API: >1
        if COMPONENT_REGISTRY.model_api < 2:
            self.log.warning("Skipping semaphore cleanup since minimum model "
                             "API is %s (needs >= 2)",
                             COMPONENT_REGISTRY.model_api)
            return

        for semaphore_name in self.getSemaphores():
            for holder in self.semaphoreHolders(semaphore_name):
                if isinstance(holder, str):
                    self.log.warning(
                        "Ignoring legacy semaphore holder %s for semaphore %s",
                        holder, semaphore_name)
                    continue
                if (self.kazoo_client.exists(holder["buildset_path"])
                        is not None):
                    continue

                semaphore_key = quote_plus(semaphore_name)
                semaphore_path = f"{self.tenant_root}/{semaphore_key}"
                self.log.error("Releasing leaked semaphore %s held by %s",
                               semaphore_path, holder)
                self._release(self.log, semaphore_path, holder, quiet=False)
