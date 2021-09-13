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

import logging
import threading
import queue

import cachetools


class Times:
    """Perform asynchronous database queries to estimate build times.

    To avoid allowing the SQL database to become a bottelneck when
    launching builds, this class performs asynchronous queries against
    the DB and returns estimated build times.

    This is intended as a temporary hedge against performance
    regressions during Zuul v4 development and can likely be removed
    once multiple schedulers are supported and possible tightening of
    database requirements.
    """

    log = logging.getLogger("zuul.times")

    def __init__(self, sql, statsd):
        self.sql = sql
        self.statsd = statsd
        self.queue = queue.Queue()
        self.cache = cachetools.TTLCache(8192, 3600)
        self.thread = threading.Thread(target=self.run)
        self.running = False

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.queue.put(None)

    def join(self):
        return self.thread.join()

    def run(self):
        while self.running:
            key = self.queue.get()
            if key is None:
                continue
            try:
                # Double check that we haven't added this key since it
                # was requested
                if key in self.cache:
                    continue
                with self.statsd.timer('zuul.scheduler.time_query'):
                    self._getTime(key)
            except Exception:
                self.log.exception("Error querying DB for build %s", key)

    def _getTime(self, key):
        tenant, project, branch, job = key
        previous_builds = self.sql.getBuilds(
            tenant=tenant,
            project=project,
            branch=branch,
            job_name=job,
            final=True,
            result='SUCCESS',
            limit=10,
            sort_by_buildset=True)
        times = [x.duration for x in previous_builds if x.duration]
        if times:
            estimate = float(sum(times)) / len(times)
            self.cache.setdefault(key, estimate)
        # Don't cache a zero value, so that new jobs get an estimated
        # time ASAP.

    def getEstimatedTime(self, tenant, project, branch, job):
        key = (tenant, project, branch, job)
        ret = self.cache.get(key)
        if ret is not None:
            return ret

        self.queue.put(key)
        return None
