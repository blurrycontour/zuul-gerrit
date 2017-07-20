import os
import tempfile
import time

from tests.base import BaseTestCase

from zuul.executor.server import DiskAccountant, DiskJobKiller, DirWatch


class TestDiskAccountant(BaseTestCase):
    def test_disk_accountant(self):
        dirwatch = DirWatch()
        jobsdir = tempfile.mkdtemp()
        da = DiskAccountant(jobsdir, 1, dirwatch)
        da.start()
        testdir = os.path.join(jobsdir, '012345')
        os.mkdir(testdir)
        killed = []

        def handle_kill():
            killed.append(True)  # noqa
        disk_killer = DiskJobKiller(testdir, handle_kill, dirwatch)
        disk_killer.start()

        testfile = os.path.join(testdir, 'tfile')
        with open(testfile, 'w') as tf:
            tf.write(2 * 1024 * 1024 * '.')
        # da should catch over-limit dir within 5 seconds
        for i in range(0, 50):
            if killed:
                break
            time.sleep(0.1)
        self.assertTrue(killed)
        disk_killer.stop()
        da.stop()
