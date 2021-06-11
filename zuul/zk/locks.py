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
from urllib.parse import quote_plus

from zuul.zk.exceptions import LockException

LOCK_ROOT = "/zuul/locks"
TENANT_LOCK_ROOT = f"{LOCK_ROOT}/tenant"


@contextmanager
def locked(lock, blocking=True, timeout=None):
    if not lock.acquire(blocking=blocking, timeout=timeout):
        raise LockException(f"Failed to acquire lock {lock}")
    try:
        yield
    finally:
        try:
            lock.release()
        except Exception:
            log = logging.getLogger("zuul.zk.locks")
            log.exception("Failed to release lock %s", lock)


def tenant_read_lock(client, tenant_name):
    safe_tenant = quote_plus(tenant_name)
    return client.client.ReadLock(f"{TENANT_LOCK_ROOT}/{safe_tenant}")


def tenant_write_lock(client, tenant_name):
    safe_tenant = quote_plus(tenant_name)
    return client.client.WriteLock(f"{TENANT_LOCK_ROOT}/{safe_tenant}")


def pipeline_lock(client, tenant_name, pipeline_name):
    safe_tenant = quote_plus(tenant_name)
    safe_pipeline = quote_plus(pipeline_name)
    return client.client.Lock(
        f"/zuul/locks/pipeline/{safe_tenant}/{safe_pipeline}")


def management_queue_lock(client, tenant_name):
    safe_tenant = quote_plus(tenant_name)
    return client.client.Lock(f"/zuul/locks/events/management/{safe_tenant}")


def trigger_queue_lock(client, tenant_name):
    safe_tenant = quote_plus(tenant_name)
    return client.client.Lock(f"/zuul/locks/events/trigger/{safe_tenant}")
