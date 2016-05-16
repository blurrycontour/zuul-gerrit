# Copyright 2016 Rackspace Australia
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

from tests.base import (
    BaseTestCase,
    ZuulAnsibleLauncherTestCase,
)


class TestAnsibleLaunchServer(BaseTestCase):
    def test_jjb_functions_list(self):
        pass

    def test_console_log_is_captured(self):
        pass

    def test_scp_publisher(self):
        pass

    def test_ftp_publisher(self):
        pass

    def test_timeout_wrapper(self):
        pass

    def test_unknown_jjb_functions(self):
        pass

    def test_prepare_ansible_files(self):
        pass


class TestAnsibleLaunchServerScenario(ZuulAnsibleLauncherTestCase):
    def test_get_nodes(self):
        pass

    def test_build_functions_register_with_scheduler(self):
        pass

    def test_basic_job_runs(self):
        pass
