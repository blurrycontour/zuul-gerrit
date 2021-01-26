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

import logging
from typing import List
from urllib.parse import quote_plus

from kazoo.exceptions import NoNodeError

from zuul import model
from zuul.lib.logutil import get_annotated_logger
from zuul.zk import ZooKeeperClient, ZooKeeperBase


class SemaphoreHandler(ZooKeeperBase):
    log = logging.getLogger("zuul.zk.SemaphoreHandler")

    semaphore_root = "/zuul/semaphores"
    semaphore_lock_root = "/zuul/semaphore_locks"

    def __init__(
        self, client: ZooKeeperClient, tenant_name: str, layout: model.Layout
    ):
        super().__init__(client)
        self.layout = layout
        self.tenant_root = f"{self.semaphore_root}/{tenant_name}"
        self.lock_root = f"{self.semaphore_lock_root}/{tenant_name}"

    def acquire(
        self, item: model.QueueItem, job: model.Job, request_resources: bool
    ) -> bool:
        if not job.semaphore:
            return True

        log = get_annotated_logger(self.log, item.event)
        if job.semaphore.resources_first and request_resources:
            # We're currently in the resource request phase and want to get the
            # resources before locking. So we don't need to do anything here.
            return True
        else:
            # As a safety net we want to acuire the semaphore at least in the
            # run phase so don't filter this here as re-acuiring the semaphore
            # is not a problem here if it has been already acquired before in
            # the resources phase.
            pass

        semaphore_key = quote_plus(job.semaphore.name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        self.kazoo_client.ensure_path(semaphore_path)

        lock_path = f"{self.lock_root}/{semaphore_key}"
        with self.kazoo_client.Lock(lock_path):
            semaphore_holders = self.kazoo_client.get_children(semaphore_path)

            job_key = quote_plus(job.name)
            semaphore_handle = f"{item.uuid}-{job_key}"

            if semaphore_handle in semaphore_holders:
                return True

            # semaphore is there, check max
            if len(semaphore_holders) < self._max_count(job.semaphore.name):
                self.kazoo_client.create(
                    f"{semaphore_path}/{semaphore_handle}"
                )
                log.debug(
                    "Semaphore %s acquired: job %s, item %s",
                    job.semaphore.name,
                    job.name,
                    item,
                )
                return True

            return False

    def release(self, item: model.QueueItem, job: model.Job) -> None:
        if not job.semaphore:
            return

        log = get_annotated_logger(self.log, item.event)
        semaphore_key = quote_plus(job.semaphore.name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        job_key = quote_plus(job.name)
        semaphore_handle = f"{item.uuid}-{job_key}"
        try:
            lock_path = f"{self.lock_root}/{semaphore_key}"
            with self.kazoo_client.Lock(lock_path):
                self.kazoo_client.delete(
                    f"{semaphore_path}/{semaphore_handle}"
                )
            log.debug(
                "Semaphore %s released: job %s, item %s",
                job.semaphore.name,
                job.name,
                item,
            )
        except NoNodeError:
            log.error(
                "Semaphore can not be released for %s "
                "because the semaphore is not held",
                item,
            )
            return

    def semaphore_holders(self, semaphore_name: str) -> List[str]:
        semaphore_key = quote_plus(semaphore_name)
        semaphore_path = f"{self.tenant_root}/{semaphore_key}"
        try:
            return self.kazoo_client.get_children(semaphore_path)
        except NoNodeError:
            return []

    def _max_count(self, semaphore_name: str) -> int:
        semaphore = self.layout.semaphores.get(semaphore_name)
        return 1 if semaphore is None else semaphore.max
