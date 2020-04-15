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
import socket
import time

from tests.base import ZuulTestCase


class TestPausedScheduler(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'
    wait_timeout = 2

    def setup_config(self, config_file: str):
        config = super(TestPausedScheduler, self).setup_config(config_file)
        config.set('scheduler', 'paused_on_start', 'true')
        return config

    def test_resume_on_start(self):
        """Test resume scheduler paused on start"""

        # Given
        self.create_branch('org/project', 'stable')
        self.fake_gerrit.addEvent(
            self.fake_gerrit.getFakeBranchCreatedEvent(
                'org/project', 'stable'))
        self.assertRaises(Exception, self.waitUntilSettled, "paused")

        A = self.fake_gerrit.addFakeChange('org/project', 'stable', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))

        # When: Resuming scheduler
        self.wait_timeout = 90  # reset original value
        self.scheds.first.sched.resume()
        self.waitUntilSettled("resumed")

        # Then: Work will resume normally
        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2, "A should report start and success")
        self.assertIn('gate', A.messages[1], "A should transit gate")
        self.assertEqual(self.getJobFromHistory('project-test1').node,
                         'label2')


class TestMultiScheduler(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'

    def test_pause_resume(self):
        """Test pause/resume"""

        # Given: Paused scenario
        self.create_branch('org/project', 'stable')
        self.fake_gerrit.addEvent(
            self.fake_gerrit.getFakeBranchCreatedEvent(
                'org/project', 'stable'))
        self.waitUntilSettled()
        self.wait_timeout = 2  # just not to wait too long

        # When: Pause scheduler and add some changes
        self.scheds.first.sched.pause()
        while not self.scheds.first.sched._paused_loop:
            time.sleep(0.1)

        A = self.fake_gerrit.addFakeChange('org/project', 'stable', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))

        # Then: Nothing should happen, i.e. timeout
        self.assertRaises(Exception, self.waitUntilSettled, "paused")

        # Given: Resumed scenario
        self.wait_timeout = 90  # reset original value

        # When: Resuming scheduler
        self.scheds.first.sched.resume()
        self.waitUntilSettled("resumed")

        # Then: Work will resume normally
        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2, "A should report start and success")
        self.assertIn('gate', A.messages[1], "A should transit gate")
        self.assertEqual(self.getJobFromHistory('project-test1').node,
                         'label2')

    def test_pause_resume_using_commands(self):
        """Test pause/resume using commands"""

        # Given: Paused scenario
        self.create_branch('org/project', 'stable')
        self.fake_gerrit.addEvent(
            self.fake_gerrit.getFakeBranchCreatedEvent(
                'org/project', 'stable'))
        self.waitUntilSettled()
        self.wait_timeout = 2  # just not to wait too long
        command_socket = self.config.get('scheduler', 'command_socket')

        # When: Pause scheduler and add some changes
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(command_socket)
            s.sendall('pause\n'.encode('utf8'))
        while not self.scheds.first.sched._paused_loop:
            time.sleep(0.1)

        A = self.fake_gerrit.addFakeChange('org/project', 'stable', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))

        # Then: Nothing should happen, i.e. timeout
        self.assertRaises(Exception, self.waitUntilSettled, "paused")

        # Given: Resumed scenario
        self.wait_timeout = 90  # reset original value

        # When: Resuming scheduler
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(command_socket)
            s.sendall('resume\n'.encode('utf8'))
        self.waitUntilSettled("resumed")

        # Then: Work will resume normally
        self.assertEqual(self.getJobFromHistory('project-test1').result,
                         'SUCCESS')
        self.assertEqual(self.getJobFromHistory('project-test2').result,
                         'SUCCESS')
        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(A.reported, 2, "A should report start and success")
        self.assertIn('gate', A.messages[1], "A should transit gate")
        self.assertEqual(self.getJobFromHistory('project-test1').node,
                         'label2')
