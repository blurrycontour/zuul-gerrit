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
from contextlib import contextmanager
from typing import Generator, List

from kazoo.recipe.lock import Lock, ReadLock, WriteLock

from zuul.zk import ZooKeeperClient

TENANT_LOCK_ROOT = "/zuul/locks/tenant"


class LockFailedError(RuntimeError):
    pass


@contextmanager
def locked(
    *locks: Lock, blocking=True, timeout=None, ephemeral=True
) -> Generator[None, None, None]:
    need_release: List[Lock] = []
    try:
        for lock in locks:
            if not lock.acquire(
                blocking=blocking, timeout=timeout, ephemeral=ephemeral
            ):
                raise LockFailedError("Failed to aquire lock {}".format(lock))
            need_release.append(lock)
        yield
    finally:
        for lock in need_release:
            try:
                lock.release()
            except Exception:
                log = logging.getLogger("zuul.zk.locks")
                log.exception("Failed to release lock %s", lock)


def tenant_read_lock(
    client: ZooKeeperClient, tenant_name: str
) -> ReadLock:
    lock_path = "/".join((TENANT_LOCK_ROOT, tenant_name))
    return client.kazoo_client.ReadLock(lock_path)


def tenant_write_lock(
    client: ZooKeeperClient, tenant_name: str
) -> WriteLock:
    lock_path = "/".join((TENANT_LOCK_ROOT, tenant_name))
    return client.kazoo_client.WriteLock(lock_path)


def pipeline_lock(
    client: ZooKeeperClient, tenant_name: str, pipeline_name: str
) -> Lock:
    return client.kazoo_client.Lock(
        "/zuul/locks/pipeline/{}/{}".format(tenant_name, pipeline_name)
    )


def event_queue_lock(client: ZooKeeperClient, queue_name: str) -> Lock:
    return client.kazoo_client.Lock("/zuul/locks/events/{}".format(queue_name))
