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
from enum import Enum
from typing import Any, Dict, Generator, Optional

from kazoo.exceptions import LockTimeout, NoNodeError
from kazoo.protocol.states import ZnodeStat
from kazoo.recipe.lock import Lock

from zuul.lib.logutil import get_annotated_logger
from zuul.zk import ZooKeeperBase, ZooKeeperClient
from zuul.zk.event_queues import MergerEventResultFuture
from zuul.zk.exceptions import MergeJobNotFound


class MergeJobState(Enum):
    REQUESTED = 0
    RUNNING = 1
    COMPLETED = 2


class MergeJobType(Enum):
    MERGE = 0
    CAT = 1
    REF_STATE = 2
    FILES_CHANGES = 3


class MergeJob:
    def __init__(
        self,
        uuid: str,
        state: MergeJobState,
        job_type: MergeJobType,
        payload: Dict[str, Any],
        precedence: int,
        build_set_uuid: Optional[str],
        tenant_name: Optional[str],
        pipeline_name: Optional[str],
        queue_name: Optional[str],
    ):
        self.uuid = uuid
        self.state = state
        self.job_type = job_type
        self.payload = payload
        self.precedence = precedence
        self.build_set_uuid = build_set_uuid
        self.tenant_name = tenant_name
        self.pipeline_name = pipeline_name
        self.queue_name = queue_name

        # Path to the future result if requested
        self.result_path: Optional[str] = None

        # ZK related data
        self.path: Optional[str] = None
        self._zstat: Optional[ZnodeStat] = None
        self.lock: Optional[Lock] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "state": self.state.name,
            "job_type": self.job_type.name,
            "payload": self.payload,
            "precedence": self.precedence,
            "build_set_uuid": self.build_set_uuid,
            "tenant_name": self.tenant_name,
            "pipeline_name": self.pipeline_name,
            "queue_name": self.queue_name,
            "result_path": self.result_path,
        }

    @classmethod
    def from_dict(cls, data) -> "MergeJob":
        job = cls(
            data["uuid"],
            MergeJobState[data["state"]],
            MergeJobType[data["job_type"]],
            data["payload"],
            data["precedence"],
            data["build_set_uuid"],
            data["tenant_name"],
            data["pipeline_name"],
            data["queue_name"],
        )
        job.result_path = data.get("result_path")
        return job

    def __lt__(self, other) -> bool:
        # Sort jobs by precedence and their creation time in ZooKeeper in
        # ascending order to prevent older jobs from starving.
        if self.precedence == other.precedence:
            if self._zstat and other._zstat:
                return self._zstat.ctime < other._zstat.ctime
            return self.uuid < other.uuid
        return self.precedence < other.precedence

    def __eq__(self, other) -> bool:
        same_prec = self.precedence == other.precedence
        if self._zstat and other._zstat:
            same_ctime = self._zstat.ctime == other._zstat.ctime
        else:
            same_ctime = self.uuid == other.uuid

        return same_prec and same_ctime

    def __repr__(self) -> str:
        return (
            f"<MergeJob uuid={self.uuid} job_type={self.job_type.name} "
            f"state={self.state.name} path={self.path}>"
        )


class MergeJobQueue(ZooKeeperBase):
    ROOT = "/zuul/merges"
    LOCK_ROOT = "/zuul/merge-locks"
    RESULTS_ROOT = "/zuul/results/merges"

    log = logging.getLogger("zuul.zk.merges.MergeJobQueue")

    def __init__(self, client: ZooKeeperClient):
        super().__init__(client)

    def _iter_merge_jobs(self):
        jobs = []
        try:
            jobs = self.kazoo_client.get_children(self.ROOT)
        except NoNodeError:
            return

        for uuid in jobs:
            job = self.get("/".join([self.ROOT, uuid]))
            # Do not yield NoneType jobs
            if job:
                yield job

    def in_state(
        self, *states: MergeJobState
    ) -> Generator[MergeJob, None, None]:
        if not states:
            states = tuple(MergeJobState)

        jobs = list(
            filter(lambda j: j.state in states, self._iter_merge_jobs())
        )

        return (j for j in sorted(jobs))

    def next(self) -> Generator[MergeJob, None, None]:
        yield from self.in_state(MergeJobState.REQUESTED)

    def submit(
        self, job: MergeJob, needs_result: bool = False, event=None
    ) -> Optional[MergerEventResultFuture]:
        log = get_annotated_logger(self.log, event=event)

        path = "/".join([self.ROOT, job.uuid])
        result = None

        # If a result is needed, create the result_path with the same uuid and
        # store it on the job, so the merger server can store the result there.
        if needs_result:
            job.result_path = "/".join([self.RESULTS_ROOT, job.uuid])
            result = MergerEventResultFuture(self.client, job.result_path)

        log.debug("Submitting merge job to ZooKeeper %s", job)

        self.kazoo_client.create(
            path, self._dict_to_bytes(job.to_dict()), makepath=True
        )

        return result

    def get(self, path: str) -> Optional[MergeJob]:
        try:
            data, zstat = self.kazoo_client.get(path)
        except NoNodeError:
            return None

        if not data:
            return None

        content = self._bytes_to_dict(data)
        job = MergeJob.from_dict(content)
        job.path = path
        job._zstat = zstat

        return job

    def update(self, job: MergeJob) -> None:
        self.log.debug("Updating merge job in path %s", job.path)

        if job._zstat is None:
            self.log.debug(
                "Cannot update job %s: Missing version information.",
                job.uuid,
            )
            return
        try:
            zstat = self.kazoo_client.set(
                job.path,
                self._dict_to_bytes(job.to_dict()),
                version=job._zstat.version,
            )
            # Update the zstat on the job after updating the ZK node
            job._zstat = zstat
        except NoNodeError:
            raise MergeJobNotFound(f"Could not udpate {job.path}")

    def report_result(self, job: MergeJob, result: Dict[str, Any]) -> None:
        self.kazoo_client.create(
            job.result_path,
            self._dict_to_bytes(result),
            makepath=True,
        )

    def remove(self, job: MergeJob) -> None:
        try:
            self.kazoo_client.delete(job.path)
        except NoNodeError:
            # Nothing to do if the node is already deleted
            pass

    # TODO (felix): Find lost merge jobs

    def lock(
        self, job: MergeJob, blocking: bool = True, timeout: int = None
    ) -> bool:
        path = "/".join([self.LOCK_ROOT, job.uuid])
        have_lock = False
        lock = None
        try:
            lock = Lock(self.kazoo_client, path)
            have_lock = lock.acquire(blocking, timeout)
        except LockTimeout:
            have_lock = False
            self.log.error("Timeout trying to acquire lock %s", job.path)
        except NoNodeError:
            have_lock = False
            self.log.error("MergeJob not found for locking: %s", job.uuid)

        # If we aren't blocking, it's possible we didn't get the lock because
        # someone else has it.
        if not have_lock:
            return False

        job.lock = lock
        return True

    def unlock(self, job: MergeJob) -> None:
        if job.lock is None:
            self.log.warning("Job %s does not hold a lock", job)
        else:
            job.lock.release()
            job.lock = None
