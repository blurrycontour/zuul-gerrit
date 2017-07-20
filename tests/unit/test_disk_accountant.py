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

import os
import tempfile
import time

from tests.base import BaseTestCase

from zuul.executor.server import DiskAccountant


class FakeExecutor(object):
    def __init__(self):
        self.stopped_jobs = set()

    def stopJobByJobDir(self, jobdir):
        self.stopped_jobs.add(jobdir)


class TestDiskAccountant(BaseTestCase):
    def test_disk_accountant(self):
        jobsdir = tempfile.mkdtemp()
        executor_server = FakeExecutor()
        da = DiskAccountant(jobsdir, 1, executor_server.stopJobByJobDir)
        da.start()
        testdir = os.path.join(jobsdir, '012345')
        os.mkdir(testdir)

        testfile = os.path.join(testdir, 'tfile')
        with open(testfile, 'w') as tf:
            tf.write(2 * 1024 * 1024 * '.')
        # da should catch over-limit dir within 5 seconds
        for i in range(0, 50):
            if testdir in executor_server.stopped_jobs:
                break
            time.sleep(0.1)
        self.assertEqual(set([testdir]), executor_server.stopped_jobs)
        da.stop()
        self.assertFalse(da.thread.is_alive())
