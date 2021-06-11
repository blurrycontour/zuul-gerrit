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
from contextlib import contextmanager

LOCK_ROOT = "/zuul/locks"
TENANT_LOCK_ROOT = f"{LOCK_ROOT}/tenant"


class LockFailedError(RuntimeError):
    pass


@contextmanager
def locked(*locks, blocking=True, timeout=None, ephemeral=True):
    need_release = []
    try:
        for lock in locks:
            if not lock.acquire(blocking=blocking, timeout=timeout,
                                ephemeral=ephemeral):
                raise LockFailedError(f"Failed to aquire lock {lock}")
            need_release.append(lock)
        yield
    finally:
        for lock in need_release:
            try:
                lock.release()
            except Exception:
                log = logging.getLogger("zuul.zk.locks")
                log.exception("Failed to release lock %s", lock)


def tenant_read_lock(client, tenant_name):
    return client.client.ReadLock(f"{TENANT_LOCK_ROOT}/{tenant_name}")


def tenant_write_lock(client, tenant_name):
    return client.client.WriteLock(f"{TENANT_LOCK_ROOT}/{tenant_name}")


def pipeline_lock(client, tenant_name, pipeline_name):
    return client.client.Lock(
        f"/zuul/locks/pipeline/{tenant_name}/{pipeline_name}")


def event_queue_lock(client, queue_name):
    return client.client.Lock(f"/zuul/locks/events/{queue_name}")
