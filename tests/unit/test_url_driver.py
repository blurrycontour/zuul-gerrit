# Copyright 2019 Red Hat, Inc.
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

import os
import re
import time
import threading
import socketserver
import http.server

from tests.base import ZuulTestCase


class FakeWebServer(object):

    def __init__(self, test_root):
        self.test_root = test_root

    def start(self):

        class Server(http.server.SimpleHTTPRequestHandler):

            self.test_root = self.test_root

            def translate_path(self, path):
                path = super(Server, self).translate_path(path)
                return re.sub(os.getcwd(), self.test_root, path)

        Server.test_root = self.test_root
        self.httpd = socketserver.ThreadingTCPServer(('', 0), Server)
        self.port = self.httpd.socket.getsockname()[1]
        self.thread = threading.Thread(name='FakeWebServer',
                                       target=self.httpd.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.thread.join()


class TestURLDriver(ZuulTestCase):
    tenant_config_file = 'config/url-driver/main.yaml'

    def setUp(self):
        super(TestURLDriver, self).setUp()
        self.web_server = FakeWebServer(self.test_root)
        self.web_server.start()

    def tearDown(self):
        self.web_server.stop()
        super(TestURLDriver, self).tearDown()

    def wait_for_triggered(self):
        pipeline = self.sched.abide.tenants[
            'tenant-one'].layout.pipelines.get('urltrigger')
        trigger = pipeline.triggers[0]
        count_ref = trigger.driver.trigger_count
        sleep_count = 0
        while True:
            if sleep_count >= 5:
                break
            if trigger.driver.trigger_count > count_ref:
                break
            time.sleep(1)
            sleep_count += 1

    def test_check_job_triggered(self):
        # Set the remote resource
        open(os.path.join(
            self.test_root, 'artifact.tgz'), 'w').write('content')

        # Set the pipeline, job and project's pipeline conf
        attr_dict = {
            'path1': 'http://localhost:%s/artifact.tgz' % (
                self.web_server.port),
            'path2': 'http://localhost:%s/notexists.tgz' % (
                self.web_server.port)}
        self.commitConfigUpdate(
            'common-config', 'layouts/url.yaml', attr_dict)
        self.sched.reconfigure(self.config)
        self.waitUntilSettled()

        self.wait_for_triggered()
        self.waitUntilSettled()

        # Ensure no jobs have run
        self.assertEqual(len(self.history), 0)

        # Now make a change in the resource
        open(os.path.join(
            self.test_root, 'artifact.tgz'), 'w').write('changed')

        self.wait_for_triggered()
        self.waitUntilSettled()

        # Make sure the related job has been triggered
        # but only 1 job has run
        self.assertHistory([
            dict(name='project-test', result='SUCCESS',
                 ref='refs/heads/master'),
        ], ordered=False)
