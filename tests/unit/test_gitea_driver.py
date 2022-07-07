# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2016 Red Hat, Inc.
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

import socket

from zuul.lib import strings
from tests.base import ZuulTestCase, simple_layout
from tests.base import ZuulWebFixture


class TestGiteaDriver(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_pull_request_opened(self):

        initial_comment = "This is the\nPR initial_comment."
        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A', initial_comment=initial_comment)
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

        job = self.getJobFromHistory('project-test2')
        zuulvars = job.parameters['zuul']
        self.assertEqual(str(A.number), zuulvars['change'])
        self.assertEqual(str(A.head_sha), zuulvars['patchset'])
        self.assertEqual('master', zuulvars['branch'])
        self.assertEquals('https://fakegitea.com/org/project/pulls/1',
                          zuulvars['items'][0]['change_url'])
        self.assertEqual(zuulvars["message"],
                         strings.b64encode(initial_comment))
        self.assertEqual(2, len(self.history))


class TestGiteaWebhook(ZuulTestCase):
    config_file = 'zuul-gitea-driver.conf'

    def setUp(self):
        super(TestGiteaWebhook, self).setUp()
        # Start the web server
        self.web = self.useFixture(
            ZuulWebFixture(self.changes, self.config,
                           self.additional_event_queues, self.upstream_root,
                           self.poller_events,
                           self.git_url_with_auth, self.addCleanup,
                           self.test_root))

        host = '127.0.0.1'
        # Wait until web server is started
        while True:
            port = self.web.port
            try:
                with socket.create_connection((host, port)):
                    break
            except ConnectionRefusedError:
                pass

        self.fake_gitea.setZuulWebPort(port)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_webhook(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent(),
                                  use_zuulweb=False,
                                  project='org/project')
        self.waitUntilSettled()
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)

    @simple_layout('layouts/basic-gitea.yaml', driver='gitea')
    def test_webhook_via_zuulweb(self):

        A = self.fake_gitea.openFakePullRequest(
            'org/project', 'master', 'A')
        self.fake_gitea.emitEvent(A.getPullRequestOpenedEvent(),
                                  use_zuulweb=True,
                                  project='org/project')
        self.waitUntilSettled()

        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test1').result)
        self.assertEqual('SUCCESS',
                         self.getJobFromHistory('project-test2').result)
