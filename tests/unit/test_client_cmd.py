# Copyright 2017 Red Hat, Inc.
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

import fixtures
import json
import os

from tests.base import BaseTestCase, FIXTURE_DIR
from zuul.cmd import client as zuul_client


class TestZuulClient(BaseTestCase):

    def setUp(self):
        super(TestZuulClient, self).setUp()

        # We mock out at the gear level, rather than RPCClient object
        # level, so that we're testing as much as possible of the
        # RPCClient marshalling code.
        self.mock_gear = self.useFixture(
            fixtures.MockPatch('gear.Client', autospec=True)).mock
        self.mock_gear_job = self.useFixture(
            fixtures.MockPatch('gear.TextJob', autospec=True)).mock
        self.mock_gear_job.return_value.complete = True
        self.mock_gear_job.return_value.failure = False
        self.mock_gear_job.return_value.exception = False

    def patch_argv(self, *args):
        conf_path = os.path.join(FIXTURE_DIR, 'zuul.conf')
        argv = ["zuul", "-c", conf_path]
        argv.extend(args)
        self.useFixture(fixtures.MonkeyPatch('sys.argv', argv))

    # Common asserts to check the command-line ended up with the
    # expected RPC arguments to the remote end.
    def check_job_submission(self, name, data):
        # We should have only submitted one job per test
        self.assertEqual(self.mock_gear_job.call_count, 1)
        # Job name
        call_name = self.mock_gear_job.call_args[0][0]
        # The gear job marshalls into a json string
        call_args_json = self.mock_gear_job.call_args[0][1]
        call_args = json.loads(call_args_json)
        self.assertEqual(name, call_name)
        self.assertDictEqual(data, call_args)

    def test_autohold(self):
        self.patch_argv("autohold",
                        "--tenant", "openstack",
                        "--project", 'openstack/example_project',
                        "--job", "job-name",
                        "--reason", "A string reason",
                        "--count", "2")

        zuul_client.main()

        self.check_job_submission('zuul:autohold',
                                  {'tenant': 'openstack',
                                   'project': 'openstack/example_project',
                                   'job': 'job-name',
                                   'count': 2,
                                   'reason': 'A string reason'})

    def test_autohold_list(self):
        self.patch_argv("autohold-list")

        # mock some returned data
        self.mock_gear_job.return_value.data = [json.dumps(
            {'openstack,openstack/example_project,job-name':
             ['2', 'A string reason']})]

        zuul_client.main()
        # check the pretty-print?
        self.check_job_submission('zuul:autohold_list', {})

    def test_show_running(self):
        self.patch_argv("show", "running-jobs")

        # mock some returned data
        self.mock_gear_job.return_value.data = [json.dumps([])]
        zuul_client.main()
        # TODO(ianw): check data & print functions
        self.check_job_submission('zuul:get_running_jobs', {})

    def test_enqueue(self):
        # Testing a manual trigger of a periodic job
        self.patch_argv("enqueue",
                        "--tenant", "openstack",
                        "--trigger", "gerrit",
                        "--pipeline", "check",
                        "--project", "openstack/example_project",
                        "--change", "12345,6")

        zuul_client.main()

        self.check_job_submission('zuul:enqueue',
                                  {'tenant': 'openstack',
                                   'pipeline': 'check',
                                   'project': 'openstack/example_project',
                                   'trigger': 'gerrit',
                                   'change': '12345,6'})

    def test_promote(self):
        self.patch_argv("promote",
                        "--tenant", "openstack",
                        "--pipeline", "check",
                        "--changes", "12345,6", "65432,1")

        zuul_client.main()

        self.check_job_submission('zuul:promote',
                                  {'tenant': 'openstack',
                                   'pipeline': 'check',
                                   'change_ids': ['12345,6', '65432,1']})

    def test_enqueue_ref_periodic(self):
        # Testing a manual trigger of a periodic job
        self.patch_argv("enqueue-ref",
                        "--tenant", "openstack",
                        "--trigger", "timer",
                        "--pipeline", "periodic",
                        "--project", "openstack/example_project",
                        "--ref", "refs/head/master")

        zuul_client.main()

        self.check_job_submission('zuul:enqueue_ref',
                                  {'tenant': 'openstack',
                                   'pipeline': 'periodic',
                                   'project': 'openstack/example_project',
                                   'trigger': 'timer',
                                   'ref': 'refs/head/master',
                                   'oldrev': 40 * '0',
                                   'newrev': 40 * '0'})
