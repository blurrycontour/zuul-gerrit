# Copyright 2018 BMW Car IT GmbH
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
import math
import psutil

from zuul.executor.sensors import SensorInterface
from zuul.lib.config import get_default

CGROUP_LIMIT_FILE = '/sys/fs/cgroup/memory/memory.limit_in_bytes'
CGROUP_USAGE_FILE = '/sys/fs/cgroup/memory/memory.usage_in_bytes'


def get_avail_mem_pct():
    avail_mem_pct = 100.0 - psutil.virtual_memory().percent
    return avail_mem_pct


def get_avail_mem_pct_cgroup():
    limit = get_cgroup_value(CGROUP_LIMIT_FILE)
    usage = get_cgroup_value(CGROUP_USAGE_FILE)

    if math.inf(limit) or math.inf(usage):
        # pretend we have all memory available if we got infs
        return 100

    return 100.0 - usage / limit * 100


def get_cgroup_value(file):
    try:
        with open(file) as f:
            # If we have no limit we get a really large number back so
            # compare that with the total system memory. If it's lower
            # than the total system memory we have a cgroup limit we should
            # check.
            return int(f.read().strip())
    except Exception:
        return math.inf


def get_cgroup_limit():
    limit = get_cgroup_value(CGROUP_LIMIT_FILE)
    mem_total = psutil.virtual_memory().total
    if limit < mem_total:
        return limit
    else:
        return math.inf


class RAMSensor(SensorInterface):
    log = logging.getLogger("zuul.executor.sensor.ram")

    def __init__(self, config=None):
        self.min_avail_mem = float(get_default(config, 'executor',
                                               'min_avail_mem', '5.0'))

        self.cgroup_limit = get_cgroup_limit()

    def isOk(self):
        avail_mem_pct = get_avail_mem_pct()

        if avail_mem_pct < self.min_avail_mem:
            return False, "low memory {:3.1f}% < {}".format(
                avail_mem_pct, self.min_avail_mem)

        if math.isinf(self.cgroup_limit):
            # we have no cgroup defined limit so we're done now
            return True, "{:3.1f}% <= {}".format(
                avail_mem_pct, self.min_avail_mem)

        avail_mem_pct_cgroup = get_avail_mem_pct_cgroup()
        if avail_mem_pct_cgroup < self.min_avail_mem:
            return False, "low memory cgroup {:3.1f}% < {}".format(
                avail_mem_pct_cgroup, self.min_avail_mem)

        return True, "{:3.1f}% <= {}, {:3.1f}% <= {}".format(
            avail_mem_pct, self.min_avail_mem,
            avail_mem_pct_cgroup, self.min_avail_mem)

    def reportStats(self, statsd, base_key):
        avail_mem_pct = get_avail_mem_pct()

        statsd.gauge(base_key + '.pct_used_ram',
                     int((100.0 - avail_mem_pct) * 100))

        if math.isfinite(self.cgroup_limit):
            avail_mem_pct_cgroup = get_avail_mem_pct_cgroup()
            statsd.gauge(base_key + '.pct_used_ram_cgroup',
                         int((100.0 - avail_mem_pct_cgroup) * 100))
