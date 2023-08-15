# Copyright 2019 BMW Group
#
# This module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

import re
import textwrap

from zuul.model import PromoteEvent

from tests.base import (
    iterate_timeout,
    simple_layout,
    ZuulGithubAppTestCase,
    ZuulTestCase,
)


class TestGerritCircularDependencies(ZuulTestCase):
    config_file = "zuul-gerrit-github.conf"
    tenant_config_file = "config/circular-dependencies/main.yaml"

    def _test_simple_cycle(self, project1, project2):
        A = self.fake_gerrit.addFakeChange(project1, "master", "A")
        B = self.fake_gerrit.addFakeChange(project2, "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    def _test_transitive_cycle(self, project1, project2, project3):
        A = self.fake_gerrit.addFakeChange(project1, "master", "A")
        B = self.fake_gerrit.addFakeChange(project2, "master", "B")
        C = self.fake_gerrit.addFakeChange(project3, "master", "C")

        # A -> B -> C -> A (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        C.addApproval("Approved", 1)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_single_project_cycle(self):
        self._test_simple_cycle("org/project", "org/project")

    def test_crd_cycle(self):
        self._test_simple_cycle("org/project1", "org/project2")

    def test_single_project_transitive_cycle(self):
        self._test_transitive_cycle(
            "org/project1", "org/project1", "org/project1"
        )

    def test_crd_transitive_cycle(self):
        self._test_transitive_cycle(
            "org/project", "org/project1", "org/project2"
        )

    def test_enqueue_order(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")

        # A <-> B and A -> C (via commit-depends)
        A.data[
            "commitMessage"
        ] = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            A.subject, B.data["url"], C.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueuing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

        self.assertHistory([
            # Change A (check + gate)
            dict(name="project1-job", result="SUCCESS", changes="3,1 1,1 2,1"),
            dict(name="project-vars-job", result="SUCCESS",
                 changes="3,1 1,1 2,1"),
            dict(name="project1-job", result="SUCCESS", changes="3,1 1,1 2,1"),
            dict(name="project-vars-job", result="SUCCESS",
                 changes="3,1 1,1 2,1"),
            # Change B (check + gate)
            dict(name="project-job", result="SUCCESS", changes="3,1 2,1 1,1"),
            dict(name="project-job", result="SUCCESS", changes="3,1 1,1 2,1"),
            # Change C (check + gate)
            dict(name="project2-job", result="SUCCESS", changes="3,1"),
            dict(name="project2-job", result="SUCCESS", changes="3,1"),
        ], ordered=False)

    def test_forbidden_cycle(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project3", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "-1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "-1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 1)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

    def test_git_dependency_with_cycle(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")

        # A -> B (git) -> C -> A
        A.setDependsOn(B, 1)
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        self.executor_server.hold_jobs_in_build = True
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_dependency_on_cycle(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")

        # A -> B -> C -> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, B.data["url"]
        )

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_dependent_change_on_cycle(self):
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")

        A.setDependsOn(B, 1)
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, B.data["url"]
        )

        A.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Code-Review", 2)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 3)

        # Make sure the out-of-cycle change (A) is enqueued after the cycle.
        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")
        queue_change_numbers = []
        for queue in tenant.layout.pipelines["gate"].queues:
            for item in queue.queue:
                queue_change_numbers.append(item.change.number)
        self.assertEqual(queue_change_numbers, ['2', '3', '1'])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_cycle_dependency_on_cycle(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")
        D = self.fake_gerrit.addFakeChange("org/project2", "master", "D")

        # A -> B -> A + C
        # C -> D -> C
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data[
            "commitMessage"
        ] = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            B.subject, A.data["url"], C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, D.data["url"]
        )
        D.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            D.subject, C.data["url"]
        )

        self.fake_gerrit.addEvent(D.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(D.patchsets[-1]["approvals"]), 1)
        self.assertEqual(D.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(D.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        D.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Approved", 1)
        D.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(D.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")
        self.assertEqual(D.data["status"], "MERGED")

    def test_cycle_failure(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.executor_server.failJob("project-job", A)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "-1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        self.executor_server.failJob("project-job", A)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertIn("bundle", A.messages[-1])
        self.assertIn("bundle", B.messages[-1])
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

    @simple_layout('layouts/circular-deps-node-failure.yaml')
    def test_cycle_failed_node_request(self):
        # Test a node request failure as part of a dependency cycle

        # Pause nodepool so we can fail the node request later
        self.fake_nodepool.pause()

        A = self.fake_gerrit.addFakeChange("org/project1", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project2", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        # Fail the node request and unpause
        req = self.fake_nodepool.getNodeRequests()
        self.fake_nodepool.addFailRequest(req[0])

        self.fake_nodepool.unpause()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertIn("bundle", A.messages[-1])
        self.assertIn("bundle", B.messages[-1])
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

    def test_failing_cycle_behind_failing_change(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project", "master", "C")
        D = self.fake_gerrit.addFakeChange("org/project", "master", "D")
        E = self.fake_gerrit.addFakeChange("org/project", "master", "E")

        # C <-> D (via commit-depends)
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, D.data["url"]
        )
        D.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            D.subject, C.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        D.addApproval("Code-Review", 2)
        E.addApproval("Code-Review", 2)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        # Make sure we enqueue C as part of the circular dependency with D, so
        # we end up with the following queue state: A, B, C, ...
        C.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(D.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(E.addApproval("Approved", 1))
        self.waitUntilSettled()

        # Fail a job of the circular dependency
        self.executor_server.failJob("project-job", D)
        self.executor_server.release("project-job", change="4 1")

        # Fail job for item B ahead of the circular dependency so that this
        # causes a gate reset and item C and D are moved behind item A.
        self.executor_server.failJob("project-job", B)
        self.executor_server.release("project-job", change="2 1")
        self.waitUntilSettled()

        # Don't fail any other jobs
        self.executor_server.fail_tests.clear()
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "NEW")
        self.assertEqual(C.data["status"], "MERGED")
        self.assertEqual(D.data["status"], "MERGED")
        self.assertEqual(E.data["status"], "MERGED")

        self.assertHistory([
            dict(name="project-job", result="SUCCESS", changes="1,1"),
            dict(name="project-job", result="FAILURE", changes="1,1 2,1"),
            # First attempt of change C and D before gate reset due to change B
            dict(name="project-job", result="FAILURE",
                 changes="1,1 2,1 3,1 4,1"),
            dict(name="project-job", result="FAILURE",
                 changes="1,1 2,1 3,1 4,1"),
            dict(name="project-job", result="ABORTED",
                 changes="1,1 2,1 3,1 4,1 5,1"),
            dict(name="project-job", result="SUCCESS", changes="1,1 3,1 4,1"),
            dict(name="project-job", result="SUCCESS", changes="1,1 3,1 4,1"),
            dict(name="project-job", result="SUCCESS",
                 changes="1,1 3,1 4,1 5,1"),
        ], ordered=False)

    def test_dependency_on_cycle_failure(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Code-Review", 2)
        C.addApproval("Approved", 1)

        # A -> B -> C -> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, C.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, B.data["url"]
        )

        self.executor_server.failJob("project2-job", C)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertIn("depends on a change that failed to merge",
                      A.messages[-1])
        self.assertTrue(re.search(r'Change http://localhost:\d+/2 is needed',
                        A.messages[-1]))
        self.assertFalse(re.search('Change .*? can not be merged',
                         A.messages[-1]))

        self.assertIn("bundle that failed.", B.messages[-1])
        self.assertFalse(re.search('Change http://localhost:.*? is needed',
                         B.messages[-1]))
        self.assertFalse(re.search('Change .*? can not be merged',
                         B.messages[-1]))

        self.assertIn("bundle that failed.", C.messages[-1])
        self.assertFalse(re.search('Change http://localhost:.*? is needed',
                         C.messages[-1]))
        self.assertFalse(re.search('Change .*? can not be merged',
                         C.messages[-1]))

        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")
        self.assertEqual(C.data["status"], "NEW")

    def test_cycle_dependency_on_change(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")

        # A -> B -> A + C (git)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )
        B.setDependsOn(C, 1)

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_failing_cycle_dependency_on_change(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        C.addApproval("Code-Review", 2)
        C.addApproval("Approved", 1)

        # A -> B -> A + C (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data[
            "commitMessage"
        ] = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            B.subject, A.data["url"], C.data["url"]
        )

        self.executor_server.failJob("project-job", A)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")
        self.assertEqual(C.data["status"], "MERGED")

    def test_reopen_cycle(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project2", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)

        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        items_before = tenant.layout.pipelines['gate'].getAllItems()

        # Trigger a re-enqueue of change B
        self.fake_gerrit.addEvent(B.getChangeAbandonedEvent())
        self.fake_gerrit.addEvent(B.getChangeRestoredEvent())
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        items_after = tenant.layout.pipelines['gate'].getAllItems()

        # Make sure the complete cycle was re-enqueued
        for before, after in zip(items_before, items_after):
            self.assertNotEqual(before, after)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    def test_cycle_larger_pipeline_window(self):
        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")

        # Make the gate window smaller than the length of the cycle
        for queue in tenant.layout.pipelines["gate"].queues:
            if any("org/project" in p.name for p in queue.projects):
                queue.window = 1

        self._test_simple_cycle("org/project", "org/project")

    def test_cycle_reporting_failure(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        B.fail_merge = True

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.patchsets[-1]["approvals"][-1]["value"], "-2")
        self.assertEqual(B.patchsets[-1]["approvals"][-1]["value"], "-2")
        self.assertIn("bundle", A.messages[-1])
        self.assertIn("bundle", B.messages[-1])
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

        buildsets = {bs.change: bs for bs in
                     self.scheds.first.connections.connections[
                         'database'].getBuildsets()}
        self.assertEqual(buildsets[2].result, 'MERGE_FAILURE')
        self.assertEqual(buildsets[1].result, 'FAILURE')

    def test_cycle_reporting_partial_failure(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        A.fail_merge = True

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertIn("bundle", A.messages[-1])
        self.assertIn("bundle", B.messages[-1])
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "MERGED")

    def test_gate_reset_with_cycle(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")

        # A <-> B (via depends-on)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        C.addApproval("Approved", 1)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.executor_server.failJob("project1-job", C)
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 3)
        for build in self.builds:
            self.assertTrue(build.hasChanges(A, B))
            self.assertFalse(build.hasChanges(C))

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "NEW")

    def test_independent_bundle_items(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")
        for queue in tenant.layout.pipelines["check"].queues:
            for item in queue.queue:
                self.assertIn(item, item.bundle.items)
                self.assertEqual(len(item.bundle.items), 2)

        for build in self.builds:
            self.assertTrue(build.hasChanges(A, B))

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

    def test_gate_correct_commits(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")
        D = self.fake_gerrit.addFakeChange("org/project", "master", "D")

        # A <-> B (via depends-on)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )
        D.setDependsOn(A, 1)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        D.addApproval("Code-Review", 2)
        C.addApproval("Approved", 1)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(D.addApproval("Approved", 1))
        self.waitUntilSettled()

        for build in self.builds:
            if build.change in ("1 1", "2 1"):
                self.assertTrue(build.hasChanges(C, B, A))
                self.assertFalse(build.hasChanges(D))
            elif build.change == "3 1":
                self.assertTrue(build.hasChanges(C))
                self.assertFalse(build.hasChanges(A))
                self.assertFalse(build.hasChanges(B))
                self.assertFalse(build.hasChanges(D))
            else:
                self.assertTrue(build.hasChanges(C, B, A, D))

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(D.reported, 2)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")
        self.assertEqual(D.data["status"], "MERGED")

    def test_cycle_git_dependency(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        # A -> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        # B -> A (via parent-child dependency)
        B.setDependsOn(A, 1)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    def test_cycle_git_dependency_failure(self):
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        # A -> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        # B -> A (via parent-child dependency)
        B.setDependsOn(A, 1)

        self.executor_server.failJob("project-job", A)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

    def test_independent_reporting(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.fake_gerrit.addEvent(B.getChangeAbandonedEvent())
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

    def test_cycle_merge_conflict(self):
        self.hold_merge_jobs_in_queue = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'B')

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        # We only want to have a merge failure for the first item in the queue
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        items = tenant.layout.pipelines['gate'].getAllItems()
        with self.createZKContext() as context:
            items[0].current_build_set.updateAttributes(context,
                                                        unable_to_merge=True)

        self.waitUntilSettled()

        self.hold_merge_jobs_in_queue = False
        self.merger_api.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 0)
        self.assertEqual(B.reported, 1)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

    def test_circular_config_change(self):
        define_job = textwrap.dedent(
            """
            - job:
                name: new-job
            """)
        use_job = textwrap.dedent(
            """
            - project:
                queue: integrated
                check:
                  jobs:
                    - new-job
                gate:
                  jobs:
                    - new-job
            """)
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A",
                                           files={"zuul.yaml": define_job})
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B",
                                           files={"zuul.yaml": use_job})

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    def test_circular_config_change_job_vars(self):
        org_project_files = {
            "zuul.yaml": textwrap.dedent(
                """
                - job:
                    name: project-vars-job
                    deduplicate: false
                    vars:
                      test_var: pass

                - project:
                    queue: integrated
                    check:
                      jobs:
                        - project-vars-job
                    gate:
                      jobs:
                        - project-vars-job
                """)
        }
        A = self.fake_gerrit.addFakeChange("org/project2", "master", "A",
                                           files=org_project_files)
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")

        # C <-> A <-> B (via commit-depends)
        A.data["commitMessage"] = (
            "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
                A.subject, B.data["url"], C.data["url"]
            )
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )
        C.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            C.subject, A.data["url"]
        )

        self.executor_server.hold_jobs_in_build = True
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        vars_builds = [b for b in self.builds if b.name == "project-vars-job"]
        self.assertEqual(len(vars_builds), 1)
        self.assertEqual(vars_builds[0].job.combined_variables["test_var"],
                         "pass")

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        vars_builds = [b for b in self.builds if b.name == "project-vars-job"]
        self.assertEqual(len(vars_builds), 1)
        self.assertEqual(vars_builds[0].job.combined_variables["test_var"],
                         "pass")

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        vars_builds = [b for b in self.builds if b.name == "project-vars-job"]
        self.assertEqual(len(vars_builds), 1)
        self.assertEqual(vars_builds[0].job.combined_variables["test_var"],
                         "pass")

        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.waitUntilSettled()

        vars_builds = [b for b in self.builds if b.name == "project-vars-job"]
        self.assertEqual(len(vars_builds), 3)
        for build in vars_builds:
            self.assertEqual(build.job.combined_variables["test_var"],
                             "pass")

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_circular_config_change_single_merge_job(self):
        """Regression tests to make sure that a bundle with non-live
        config changes only spawns one merge job (so that we avoid
        problems with multiple jobs arriving in the wrong order)."""

        define_job = textwrap.dedent(
            """
            - job:
                name: new-job
            """)
        use_job = textwrap.dedent(
            """
            - project:
                check:
                  jobs:
                    - new-job
                gate:
                  jobs:
                    - new-job
            """)
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A",
                                           files={"zuul.yaml": define_job})
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B",
                                           files={"zuul.yaml": use_job})

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.waitUntilSettled()
        self.hold_merge_jobs_in_queue = True

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Assert that there is a single merge job for the bundle.
        self.assertEqual(len(self.merger_api.queued()), 1)

        self.hold_merge_jobs_in_queue = False
        self.merger_api.release()
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

    def test_bundle_id_in_zuul_var(self):
        A = self.fake_gerrit.addFakeChange("org/project1", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.executor_server.hold_jobs_in_build = True

        # bundle_id should be in check build of A
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        var_zuul_items = self.builds[0].parameters["zuul"]["items"]
        self.assertEqual(len(var_zuul_items), 2)
        self.assertIn("bundle_id", var_zuul_items[0])
        bundle_id_0 = var_zuul_items[0]["bundle_id"]
        self.assertIn("bundle_id", var_zuul_items[1])
        bundle_id_1 = var_zuul_items[1]["bundle_id"]
        self.assertEqual(bundle_id_0, bundle_id_1)
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        # bundle_id should be in check build of B
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        var_zuul_items = self.builds[0].parameters["zuul"]["items"]
        self.assertEqual(len(var_zuul_items), 2)
        self.assertIn("bundle_id", var_zuul_items[0])
        bundle_id_0 = var_zuul_items[0]["bundle_id"]
        self.assertIn("bundle_id", var_zuul_items[1])
        bundle_id_1 = var_zuul_items[1]["bundle_id"]
        self.assertEqual(bundle_id_0, bundle_id_1)
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        # bundle_id should not be in check build of C
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        var_zuul_items = self.builds[0].parameters["zuul"]["items"]
        self.assertEqual(len(var_zuul_items), 1)
        self.assertNotIn("bundle_id", var_zuul_items[0])
        self.executor_server.release()
        self.waitUntilSettled()
        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        # bundle_id should be in gate jobs of A and B, but not in C
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.waitUntilSettled()
        var_zuul_items = self.builds[-1].parameters["zuul"]["items"]
        self.assertEqual(len(var_zuul_items), 3)
        self.assertIn("bundle_id", var_zuul_items[0])
        bundle_id_0 = var_zuul_items[0]["bundle_id"]
        self.assertIn("bundle_id", var_zuul_items[1])
        bundle_id_1 = var_zuul_items[1]["bundle_id"]
        self.assertEqual(bundle_id_0, bundle_id_1)
        self.assertNotIn("bundle_id", var_zuul_items[2])

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_cross_tenant_cycle(self):
        org_project_files = {
            "zuul.yaml": textwrap.dedent(
                """
                - job:
                    name: project-vars-job
                    vars:
                      test_var: pass

                - project:
                    queue: integrated
                    check:
                      jobs:
                        - project-vars-job
                    gate:
                      jobs:
                        - project-vars-job
                """)
        }
        # Change zuul config so the bundle is considered updating config
        A = self.fake_gerrit.addFakeChange("org/project2", "master", "A",
                                           files=org_project_files)
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project1", "master", "C")
        D = self.fake_gerrit.addFakeChange("org/project4", "master", "D",)

        # C <-> A <-> B (via commit-depends)
        A.data["commitMessage"] = (
            "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
                A.subject, B.data["url"], C.data["url"]
            )
        )
        # A <-> B (via commit-depends)
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )
        # A <-> C <-> D (via commit-depends)
        C.data["commitMessage"] = (
            "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
                C.subject, A.data["url"], D.data["url"]
            )
        )
        # D <-> C (via commit-depends)
        D.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            D.subject, C.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "-1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "-1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "-1")

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        D.addApproval("Code-Review", 2)

        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(D.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")
        self.assertEqual(C.data["status"], "NEW")

        D.setMerged()
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        # Pretend D was merged so we can gate the cycle
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 6)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_cycle_unknown_repo(self):
        self.init_repo("org/unknown", tag='init')
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/unknown", "master", "B")

        # A <-> B (via commit-depends)
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "-1")

        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        B.setMerged()
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 4)
        self.assertEqual(A.data["status"], "MERGED")

    def test_promote_cycle(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        B = self.fake_gerrit.addFakeChange("org/project1", "master", "B")
        C = self.fake_gerrit.addFakeChange("org/project2", "master", "C")

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(C.addApproval("Approved", 1))
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        event = PromoteEvent('tenant-one', 'gate', ["2,1"])
        self.scheds.first.sched.pipeline_management_events['tenant-one'][
            'gate'].put(event)
        self.waitUntilSettled()

        self.assertEqual(len(self.builds), 4)
        self.assertTrue(self.builds[0].hasChanges(A))
        self.assertTrue(self.builds[0].hasChanges(B))
        self.assertFalse(self.builds[0].hasChanges(C))

        self.assertTrue(self.builds[1].hasChanges(A))
        self.assertTrue(self.builds[1].hasChanges(B))
        self.assertFalse(self.builds[0].hasChanges(C))

        self.assertTrue(self.builds[3].hasChanges(B))
        self.assertTrue(self.builds[3].hasChanges(C))
        self.assertTrue(self.builds[3].hasChanges(A))

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 2)
        self.assertEqual(C.reported, 2)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")

    def test_shared_queue_removed(self):
        self.executor_server.hold_jobs_in_build = True

        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')
        C = self.fake_gerrit.addFakeChange('org/project', 'master', 'C')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)
        C.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(C.addApproval('Approved', 1))

        self.waitUntilSettled()
        self.executor_server.release('.*-merge')
        self.waitUntilSettled()
        self.executor_server.release('.*-merge')
        self.waitUntilSettled()

        # Remove the shared queue.
        self.commitConfigUpdate(
            'common-config',
            'layouts/circular-dependency-shared-queue-removed.yaml')

        self.scheds.execute(lambda app: app.sched.reconfigure(app.config))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'NEW')
        self.assertEqual(B.data['status'], 'NEW')
        self.assertEqual(C.data['status'], 'MERGED')

    def _test_job_deduplication(self):
        # We make a second scheduler here so that the first scheduler
        # can freeze the jobs for the first item, and the second
        # scheduler freeze jobs for the second.  This forces the
        # scheduler to compare a desiralized FrozenJob with a newly
        # created one and therefore show difference-in-serialization
        # issues.
        self.hold_merge_jobs_in_queue = True
        app = self.createScheduler()
        app.start()
        self.assertEqual(len(self.scheds), 2)

        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        with app.sched.run_handler_lock:
            self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
            self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
            self.waitUntilSettled(matcher=[self.scheds.first])
            self.merger_api.release(self.merger_api.queued()[0])
            self.waitUntilSettled(matcher=[self.scheds.first])

        # Hold the lock on the first scheduler so that only the second
        # will act.
        with self.scheds.first.sched.run_handler_lock:
            self.merger_api.release()
            self.waitUntilSettled(matcher=[app])

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')

    @simple_layout('layouts/job-dedup-auto-shared.yaml')
    def test_job_deduplication_auto_shared(self):
        self._test_job_deduplication()
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 3)

    @simple_layout('layouts/job-dedup-auto-unshared.yaml')
    def test_job_deduplication_auto_unshared(self):
        self._test_job_deduplication()
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is not deduplicated
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 4)

    @simple_layout('layouts/job-dedup-true.yaml')
    def test_job_deduplication_true(self):
        self._test_job_deduplication()
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 3)

    @simple_layout('layouts/job-dedup-false.yaml')
    def test_job_deduplication_false(self):
        self._test_job_deduplication()
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is not deduplicated, though it would be under auto
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 4)

    @simple_layout('layouts/job-dedup-empty-nodeset.yaml')
    def test_job_deduplication_empty_nodeset(self):
        # Make sure that jobs with empty nodesets can still be
        # deduplicated
        self._test_job_deduplication()
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 0)

    @simple_layout('layouts/job-dedup-auto-shared.yaml')
    def test_job_deduplication_failed_node_request(self):
        # Pause nodepool so we can fail the node request later
        self.fake_nodepool.pause()

        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        # Fail the node request and unpause
        for req in self.fake_nodepool.getNodeRequests():
            if req['requestor_data']['job_name'] == 'common-job':
                self.fake_nodepool.addFailRequest(req)

        self.fake_nodepool.unpause()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'NEW')
        self.assertEqual(B.data['status'], 'NEW')
        self.assertHistory([])
        self.assertEqual(len(self.fake_nodepool.history), 3)

    @simple_layout('layouts/job-dedup-auto-shared.yaml')
    def test_job_deduplication_failed_job(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)
        self.executor_server.failJob("common-job", A)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        # If we don't make sure these jobs finish first, then one of
        # the items may complete before the other and cause Zuul to
        # abort the project*-job on the other item (with a "bundle
        # failed to merge" error).
        self.waitUntilSettled()
        self.executor_server.release('project1-job')
        self.executor_server.release('project2-job')
        self.waitUntilSettled()
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'NEW')
        self.assertEqual(B.data['status'], 'NEW')
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="FAILURE", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 3)

    @simple_layout('layouts/job-dedup-false.yaml')
    def test_job_deduplication_false_failed_job(self):
        # Test that if we are *not* deduplicating jobs, we don't
        # duplicate the result on two different builds.
        # The way we check that is to retry the common-job between two
        # items, but only once, and only on one item.  The other item
        # should be unaffected.
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        # If we don't make sure these jobs finish first, then one of
        # the items may complete before the other and cause Zuul to
        # abort the project*-job on the other item (with a "bundle
        # failed to merge" error).
        self.waitUntilSettled()
        for build in self.builds:
            if build.name == 'common-job' and build.project == 'org/project1':
                break
        else:
            raise Exception("Unable to find build")
        build.should_retry = True

        # Store a reference to the queue items so we can inspect their
        # internal attributes later to double check the retry build
        # count is correct.
        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        pipeline = tenant.layout.pipelines['gate']
        items = pipeline.getAllItems()
        self.assertEqual(len(items), 2)

        self.executor_server.release('project1-job')
        self.executor_server.release('project2-job')
        self.waitUntilSettled()
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertHistory([
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result=None, changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 5)
        self.assertEqual(items[0].change.project.name, 'org/project2')
        self.assertEqual(len(items[0].current_build_set.retry_builds), 0)
        self.assertEqual(items[1].change.project.name, 'org/project1')
        self.assertEqual(len(items[1].current_build_set.retry_builds), 1)

    @simple_layout('layouts/job-dedup-auto-shared.yaml')
    def test_job_deduplication_multi_scheduler(self):
        # Test that a second scheduler can correctly refresh
        # deduplicated builds
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        app = self.createScheduler()
        app.start()
        self.assertEqual(len(self.scheds), 2)

        # Hold the lock on the first scheduler so that only the second
        # will act.
        with self.scheds.first.sched.run_handler_lock:
            self.executor_server.hold_jobs_in_build = False
            self.executor_server.release()
            self.waitUntilSettled(matcher=[app])

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)

    @simple_layout('layouts/job-dedup-noop.yaml')
    def test_job_deduplication_noop(self):
        # Test that we don't deduplicate noop (there's no good reason
        # to do so)
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        # It's tricky to get info about a noop build, but the jobs in
        # the report have the build UUID, so we make sure it's
        # different.
        a_noop = [l for l in A.messages[-1].split('\n') if 'noop' in l][0]
        b_noop = [l for l in B.messages[-1].split('\n') if 'noop' in l][0]
        self.assertNotEqual(a_noop, b_noop)

    @simple_layout('layouts/job-dedup-retry.yaml')
    def test_job_deduplication_retry(self):
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.executor_server.retryJob('common-job', A)

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'NEW')
        self.assertEqual(B.data['status'], 'NEW')
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # There should be exactly 3 runs of the job (not 6)
            dict(name="common-job", result=None, changes="2,1 1,1"),
            dict(name="common-job", result=None, changes="2,1 1,1"),
            dict(name="common-job", result=None, changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 5)

    @simple_layout('layouts/job-dedup-retry-child.yaml')
    def test_job_deduplication_retry_child(self):
        # This tests retrying a paused build (simulating an executor restart)
        # See test_data_return_child_from_retried_paused_job
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.executor_server.returnData(
            'parent-job', A,
            {'zuul': {'pause': True}}
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)

        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        self.executor_server.release('parent-job')
        self.waitUntilSettled("till job is paused")

        paused_job = self.builds[0]
        self.assertTrue(paused_job.paused)

        # Stop the job worker to simulate an executor restart
        for job_worker in self.executor_server.job_workers.values():
            if job_worker.build_request.uuid == paused_job.uuid:
                job_worker.stop()
        self.waitUntilSettled("stop job worker")

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled("all jobs are done")
        # The "pause" job might be paused during the waitUntilSettled
        # call and appear settled; it should automatically resume
        # though, so just wait for it.
        for x in iterate_timeout(60, 'paused job'):
            if not self.builds:
                break
        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertHistory([
            dict(name="parent-job", result="ABORTED", changes="2,1 1,1"),
            dict(name="project1-job", result="ABORTED", changes="2,1 1,1"),
            dict(name="project2-job", result="ABORTED", changes="2,1 1,1"),
            dict(name="parent-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 6)

    @simple_layout('layouts/job-dedup-parent-data.yaml')
    def test_job_deduplication_parent_data(self):
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        # The parent job returns data
        self.executor_server.returnData(
            'parent-job', A,
            {'zuul':
             {'artifacts': [
                 {'name': 'image',
                  'url': 'http://example.com/image',
                  'metadata': {
                      'type': 'container_image'
                  }},
             ]}}
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()

        self.assertEqual(A.data['status'], 'MERGED')
        self.assertEqual(B.data['status'], 'MERGED')
        self.assertHistory([
            dict(name="parent-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # Only one run of the common job since it's the same
            dict(name="common-child-job", result="SUCCESS", changes="2,1 1,1"),
            # The forked job depends on different parents
            # so it should run twice
            dict(name="forked-child-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="forked-child-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 6)

    def _test_job_deduplication_semaphore(self):
        "Test semaphores with max=1 (mutex) and get resources first"
        self.executor_server.hold_jobs_in_build = True

        tenant = self.scheds.first.sched.abide.tenants.get('tenant-one')
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)

        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        A.addApproval('Code-Review', 2)
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))

        self.waitUntilSettled()
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            1)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="2,1 1,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 3)
        self.assertEqual(
            len(tenant.semaphore_handler.semaphoreHolders("test-semaphore")),
            0)

    @simple_layout('layouts/job-dedup-semaphore.yaml')
    def test_job_deduplication_semaphore(self):
        self._test_job_deduplication_semaphore()

    @simple_layout('layouts/job-dedup-semaphore-first.yaml')
    def test_job_deduplication_semaphore_resources_first(self):
        self._test_job_deduplication_semaphore()

    @simple_layout('layouts/job-dedup-auto-shared-check.yaml')
    def test_job_deduplication_check(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project1', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project2', 'master', 'B')

        # A <-> B
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.release('common-job')
        self.executor_server.release('project1-job')
        self.waitUntilSettled()

        # We do this even though it results in no changes to force an
        # extra pipeline processing run to make sure we don't garbage
        # collect the item early.
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.release('project2-job')
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="project1-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project2-job", result="SUCCESS", changes="1,1 2,1"),
            # This is deduplicated
            # dict(name="common-job", result="SUCCESS", changes="2,1 1,1"),
        ], ordered=False)
        self.assertEqual(len(self.fake_nodepool.history), 3)

        # Make sure there are no leaked queue items
        tenant = self.scheds.first.sched.abide.tenants.get("tenant-one")
        pipeline = tenant.layout.pipelines["check"]
        pipeline_path = pipeline.state.getPath()
        all_items = set(self.zk_client.client.get_children(
            f"{pipeline_path}/item"))
        self.assertEqual(len(all_items), 0)

    def test_submitted_together(self):
        self.fake_gerrit._fake_submit_whole_topic = True
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    def test_submitted_together_git(self):
        self.fake_gerrit._fake_submit_whole_topic = True

        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A")
        B = self.fake_gerrit.addFakeChange('org/project1', "master", "B")
        C = self.fake_gerrit.addFakeChange('org/project1', "master", "C")
        D = self.fake_gerrit.addFakeChange('org/project1', "master", "D")
        E = self.fake_gerrit.addFakeChange('org/project1', "master", "E")
        F = self.fake_gerrit.addFakeChange('org/project1', "master", "F")
        G = self.fake_gerrit.addFakeChange('org/project1', "master", "G")
        G.setDependsOn(F, 1)
        F.setDependsOn(E, 1)
        E.setDependsOn(D, 1)
        D.setDependsOn(C, 1)
        C.setDependsOn(B, 1)
        B.setDependsOn(A, 1)

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")
        self.assertEqual(A.queried, 1)
        self.assertEqual(B.queried, 1)
        self.assertEqual(C.queried, 1)
        self.assertEqual(D.queried, 1)
        self.assertEqual(E.queried, 1)
        self.assertEqual(F.queried, 1)
        self.assertEqual(G.queried, 1)
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS",
                 changes="1,1 2,1 3,1"),
            dict(name="project-vars-job", result="SUCCESS",
                 changes="1,1 2,1 3,1"),
        ], ordered=False)

    def test_submitted_together_git_topic(self):
        self.fake_gerrit._fake_submit_whole_topic = True

        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project1', "master", "B",
                                           topic='test-topic')
        C = self.fake_gerrit.addFakeChange('org/project1', "master", "C",
                                           topic='test-topic')
        D = self.fake_gerrit.addFakeChange('org/project1', "master", "D",
                                           topic='test-topic')
        E = self.fake_gerrit.addFakeChange('org/project1', "master", "E",
                                           topic='test-topic')
        F = self.fake_gerrit.addFakeChange('org/project1', "master", "F",
                                           topic='test-topic')
        G = self.fake_gerrit.addFakeChange('org/project1', "master", "G",
                                           topic='test-topic')
        G.setDependsOn(F, 1)
        F.setDependsOn(E, 1)
        E.setDependsOn(D, 1)
        D.setDependsOn(C, 1)
        C.setDependsOn(B, 1)
        B.setDependsOn(A, 1)

        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")
        self.assertEqual(A.queried, 8)
        self.assertEqual(B.queried, 8)
        self.assertEqual(C.queried, 8)
        self.assertEqual(D.queried, 8)
        self.assertEqual(E.queried, 8)
        self.assertEqual(F.queried, 8)
        self.assertEqual(G.queried, 8)
        self.assertHistory([
            dict(name="project1-job", result="SUCCESS",
                 changes="7,1 6,1 5,1 4,1 1,1 2,1 3,1"),
            dict(name="project-vars-job", result="SUCCESS",
                 changes="7,1 6,1 5,1 4,1 1,1 2,1 3,1"),
        ], ordered=False)

    @simple_layout('layouts/submitted-together-per-branch.yaml')
    def test_submitted_together_per_branch(self):
        self.fake_gerrit._fake_submit_whole_topic = True
        self.create_branch('org/project2', 'stable/foo')
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "stable/foo", "B",
                                           topic='test-topic')

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 0)
        self.assertEqual(B.reported, 1)
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")
        self.assertIn("does not share a change queue", B.messages[-1])

    @simple_layout('layouts/deps-by-topic.yaml')
    def test_deps_by_topic(self):
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

    @simple_layout('layouts/deps-by-topic.yaml')
    def test_deps_by_topic_git_needs(self):
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')
        C = self.fake_gerrit.addFakeChange('org/project2', "master", "C",
                                           topic='other-topic')
        D = self.fake_gerrit.addFakeChange('org/project1', "master", "D",
                                           topic='other-topic')

        # Git level dependency between B and C
        B.setDependsOn(C, 1)

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(D.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(C.patchsets[-1]["approvals"]), 1)
        self.assertEqual(C.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(C.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(D.patchsets[-1]["approvals"]), 1)
        self.assertEqual(D.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(D.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        C.addApproval("Code-Review", 2)
        D.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        C.addApproval("Approved", 1)
        D.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 3)
        self.assertEqual(C.reported, 3)
        self.assertEqual(D.reported, 3)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")
        self.assertEqual(C.data["status"], "MERGED")
        self.assertEqual(D.data["status"], "MERGED")

    @simple_layout('layouts/deps-by-topic.yaml')
    def test_deps_by_topic_new_patchset(self):
        # Make sure that we correctly update the change cache on new
        # patchsets.
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertHistory([
            dict(name="check-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="check-job", result="SUCCESS", changes="1,1 2,1"),
        ], ordered=False)

        A.addPatchset()
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(2))
        self.waitUntilSettled()

        self.assertHistory([
            # Original check run
            dict(name="check-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="check-job", result="SUCCESS", changes="1,1 2,1"),
            # Second check run
            dict(name="check-job", result="SUCCESS", changes="2,1 1,2"),
        ], ordered=False)

    def test_deps_by_topic_multi_tenant(self):
        A = self.fake_gerrit.addFakeChange('org/project5', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project6', "master", "B",
                                           topic='test-topic')

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.assertEqual(len(A.patchsets[-1]["approvals"]), 1)
        self.assertEqual(A.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(A.patchsets[-1]["approvals"][0]["value"], "1")

        self.assertEqual(len(B.patchsets[-1]["approvals"]), 1)
        self.assertEqual(B.patchsets[-1]["approvals"][0]["type"], "Verified")
        self.assertEqual(B.patchsets[-1]["approvals"][0]["value"], "1")

        # We're about to add approvals to changes without adding the
        # triggering events to Zuul, so that we can be sure that it is
        # enqueuing the changes based on dependencies, not because of
        # triggering events.  Since it will have the changes cached
        # already (without approvals), we need to clear the cache
        # first.
        for connection in self.scheds.first.connections.connections.values():
            connection.maintainCache([], max_age=0)

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 4)
        self.assertEqual(B.reported, 4)
        self.assertEqual(A.data["status"], "MERGED")
        self.assertEqual(B.data["status"], "MERGED")

        self.assertHistory([
            # Check
            dict(name="project5-job-t1", result="SUCCESS", changes="1,1"),
            dict(name="project6-job-t1", result="SUCCESS", changes="2,1"),
            dict(name="project5-job-t2", result="SUCCESS", changes="2,1 1,1"),
            dict(name="project6-job-t2", result="SUCCESS", changes="1,1 2,1"),
            # Gate
            dict(name="project5-job-t2", result="SUCCESS", changes="1,1 2,1"),
            dict(name="project6-job-t2", result="SUCCESS", changes="1,1 2,1"),
        ], ordered=False)

    def test_dependency_refresh(self):
        # Test that when two changes are put into a cycle, the
        # dependencies are refreshed and items already in pipelines
        # are updated.
        self.executor_server.hold_jobs_in_build = True

        # This simulates the typical workflow where a developer only
        # knows the change id of changes one at a time.
        # The first change:
        A = self.fake_gerrit.addFakeChange("org/project", "master", "A")
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Now that it has been uploaded, upload the second change and
        # point it at the first.
        # B -> A
        B = self.fake_gerrit.addFakeChange("org/project", "master", "B")
        B.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.data["url"]
        )
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Now that the second change is known, update the first change
        # B <-> A
        A.addPatchset()
        A.data["commitMessage"] = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.data["url"]
        )
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(2))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="project-job", result="ABORTED", changes="1,1"),
            dict(name="project-job", result="ABORTED", changes="1,1 2,1"),
            dict(name="project-job", result="SUCCESS", changes="1,2 2,1"),
            dict(name="project-job", result="SUCCESS", changes="2,1 1,2"),
        ], ordered=False)

    @simple_layout('layouts/deps-by-topic.yaml')
    def test_dependency_refresh_by_topic_check(self):
        # Test that when two changes are put into a cycle, the
        # dependencies are refreshed and items already in pipelines
        # are updated.
        self.executor_server.hold_jobs_in_build = True

        # This simulates the typical workflow where a developer
        # uploads changes one at a time.
        # The first change:
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        # Now that it has been uploaded, upload the second change
        # in the same topic.
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="check-job", result="ABORTED", changes="1,1"),
            dict(name="check-job", result="SUCCESS", changes="2,1 1,1"),
            dict(name="check-job", result="SUCCESS", changes="1,1 2,1"),
        ], ordered=False)

    @simple_layout('layouts/deps-by-topic.yaml')
    def test_dependency_refresh_by_topic_gate(self):
        # Test that when two changes are put into a cycle, the
        # dependencies are refreshed and items already in pipelines
        # are updated.
        self.executor_server.hold_jobs_in_build = True

        # This simulates a workflow where a developer adds a change to
        # a cycle already in gate.
        A = self.fake_gerrit.addFakeChange('org/project1', "master", "A",
                                           topic='test-topic')
        B = self.fake_gerrit.addFakeChange('org/project2', "master", "B",
                                           topic='test-topic')
        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        A.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(B.addApproval("Approved", 1))
        self.waitUntilSettled()

        # Add a new change to the cycle.
        C = self.fake_gerrit.addFakeChange('org/project1', "master", "C",
                                           topic='test-topic')
        self.fake_gerrit.addEvent(C.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        # At the end of this process, the gate jobs should be aborted
        # because the new dpendency showed up.
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")
        self.assertEqual(C.data["status"], "NEW")
        self.assertHistory([
            dict(name="gate-job", result="ABORTED", changes="1,1 2,1"),
            dict(name="gate-job", result="ABORTED", changes="1,1 2,1"),
            dict(name="check-job", result="SUCCESS", changes="2,1 1,1 3,1"),
        ], ordered=False)


class TestGithubCircularDependencies(ZuulTestCase):
    config_file = "zuul-gerrit-github.conf"
    tenant_config_file = "config/circular-dependencies/main.yaml"
    scheduler_count = 1

    def test_cycle_not_ready(self):
        A = self.fake_github.openFakePullRequest("gh/project", "master", "A")
        B = self.fake_github.openFakePullRequest("gh/project1", "master", "B")
        C = self.fake_github.openFakePullRequest("gh/project1", "master", "C")
        A.addReview('derp', 'APPROVED')
        B.addReview('derp', 'APPROVED')
        B.addLabel("approved")
        C.addReview('derp', 'APPROVED')

        # A -> B + C (via PR depends)
        # B -> A
        # C -> A
        A.body = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            A.subject, B.url, C.url
        )
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )
        C.body = "{}\n\nDepends-On: {}\n".format(
            C.subject, A.url
        )

        self.fake_github.emitEvent(A.addLabel("approved"))
        self.waitUntilSettled()

        self.assertEqual(len(A.comments), 0)
        self.assertEqual(len(B.comments), 0)
        self.assertEqual(len(C.comments), 0)
        self.assertFalse(A.is_merged)
        self.assertFalse(B.is_merged)
        self.assertFalse(C.is_merged)

    def test_complex_cycle_not_ready(self):
        A = self.fake_github.openFakePullRequest("gh/project", "master", "A")
        B = self.fake_github.openFakePullRequest("gh/project1", "master", "B")
        C = self.fake_github.openFakePullRequest("gh/project1", "master", "C")
        X = self.fake_github.openFakePullRequest("gh/project1", "master", "C")
        Y = self.fake_github.openFakePullRequest("gh/project1", "master", "C")
        A.addReview('derp', 'APPROVED')
        A.addLabel("approved")
        B.addReview('derp', 'APPROVED')
        B.addLabel("approved")
        C.addReview('derp', 'APPROVED')
        Y.addReview('derp', 'APPROVED')
        Y.addLabel("approved")
        X.addReview('derp', 'APPROVED')

        # A -> B + C (via PR depends)
        # B -> A
        # C -> A
        # X -> A + Y
        # Y -> X
        A.body = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            A.subject, B.url, C.url
        )
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )
        C.body = "{}\n\nDepends-On: {}\n".format(
            C.subject, A.url
        )
        X.body = "{}\n\nDepends-On: {}\nDepends-On: {}\n".format(
            X.subject, Y.url, A.url
        )
        Y.body = "{}\n\nDepends-On: {}\n".format(
            Y.subject, X.url
        )

        self.fake_github.emitEvent(X.addLabel("approved"))
        self.waitUntilSettled()

        self.assertEqual(len(A.comments), 0)
        self.assertEqual(len(B.comments), 0)
        self.assertEqual(len(C.comments), 0)
        self.assertEqual(len(X.comments), 0)
        self.assertEqual(len(Y.comments), 0)
        self.assertFalse(A.is_merged)
        self.assertFalse(B.is_merged)
        self.assertFalse(C.is_merged)
        self.assertFalse(X.is_merged)
        self.assertFalse(Y.is_merged)

    def test_filter_unprotected_branches(self):
        """
        Tests that repo state filtering due to excluding unprotected branches
        doesn't break builds if the items are targeted against different
        branches.
        """
        github = self.fake_github.getGithubClient()
        self.create_branch('gh/project', 'stable/foo')
        github.repo_from_project('gh/project')._set_branch_protection(
            'master', True)
        github.repo_from_project('gh/project')._set_branch_protection(
            'stable/foo', True)
        pevent = self.fake_github.getPushEvent(project='gh/project',
                                               ref='refs/heads/stable/foo')
        self.fake_github.emitEvent(pevent)

        self.create_branch('gh/project1', 'stable/bar')
        github.repo_from_project('gh/project1')._set_branch_protection(
            'master', True)
        github.repo_from_project('gh/project1')._set_branch_protection(
            'stable/bar', True)
        pevent = self.fake_github.getPushEvent(project='gh/project',
                                               ref='refs/heads/stable/bar')
        self.fake_github.emitEvent(pevent)

        # Wait until push events are processed to pick up branch
        # protection settings
        self.waitUntilSettled()

        A = self.fake_github.openFakePullRequest(
            "gh/project", "stable/foo", "A")
        B = self.fake_github.openFakePullRequest(
            "gh/project1", "stable/bar", "B")
        A.addReview('derp', 'APPROVED')
        B.addReview('derp', 'APPROVED')
        B.addLabel("approved")

        # A <-> B
        A.body = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.url
        )
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )

        self.fake_github.emitEvent(A.addLabel("approved"))
        self.waitUntilSettled()

        self.assertEqual(len(A.comments), 2)
        self.assertEqual(len(B.comments), 2)
        self.assertTrue(A.is_merged)
        self.assertTrue(B.is_merged)

    def test_cycle_failed_reporting(self):
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_github.openFakePullRequest("gh/project", "master", "A")
        B = self.fake_github.openFakePullRequest("gh/project1", "master", "B")
        A.addReview('derp', 'APPROVED')
        B.addReview('derp', 'APPROVED')
        B.addLabel("approved")

        # A <-> B
        A.body = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.url
        )
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )

        self.fake_github.emitEvent(A.addLabel("approved"))
        self.waitUntilSettled()

        # Change draft status of A so it can no longer merge. Note that we
        # don't send an event to test the "github doesn't send an event"
        # case.
        A.draft = True
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertEqual(len(A.comments), 2)
        self.assertEqual(len(B.comments), 2)
        self.assertFalse(A.is_merged)
        self.assertFalse(B.is_merged)

        self.assertIn("part of a bundle that can not merge",
                      A.comments[-1])
        self.assertTrue(
            re.search("Change https://github.com/gh/project/pull/1 "
                      "can not be merged",
                      A.comments[-1]))
        self.assertFalse(re.search('Change .*? is needed',
                                   A.comments[-1]))

        self.assertIn("part of a bundle that can not merge",
                      B.comments[-1])
        self.assertTrue(
            re.search("Change https://github.com/gh/project/pull/1 "
                      "can not be merged",
                      B.comments[-1]))
        self.assertFalse(re.search('Change .*? is needed',
                                   B.comments[-1]))

    def test_dependency_refresh(self):
        # Test that when two changes are put into a cycle, the
        # dependencies are refreshed and items already in pipelines
        # are updated.
        self.executor_server.hold_jobs_in_build = True

        # This simulates the typical workflow where a developer only
        # knows the PR id of changes one at a time.
        # The first change:
        A = self.fake_github.openFakePullRequest("gh/project", "master", "A")
        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        # Now that it has been uploaded, upload the second change and
        # point it at the first.
        # B -> A
        B = self.fake_github.openFakePullRequest("gh/project", "master", "B")
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )
        self.fake_github.emitEvent(B.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        # Now that the second change is known, update the first change
        # B <-> A
        A.body = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.url
        )

        self.fake_github.emitEvent(A.getPullRequestEditedEvent(A.subject))
        self.waitUntilSettled()

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="project-job", result="ABORTED",
                 changes=f"{A.number},{A.head_sha}"),
            dict(name="project-job", result="SUCCESS",
                 changes=f"{A.number},{A.head_sha} {B.number},{B.head_sha}"),
            dict(name="project-job", result="SUCCESS",
                 changes=f"{B.number},{B.head_sha} {A.number},{A.head_sha}"),
        ], ordered=False)


class TestGithubAppCircularDependencies(ZuulGithubAppTestCase):
    config_file = "zuul-gerrit-github-app.conf"
    tenant_config_file = "config/circular-dependencies/main.yaml"
    scheduler_count = 1

    def test_dependency_refresh_checks_api(self):
        # Test that when two changes are put into a cycle, the
        # dependencies are refreshed and items already in pipelines
        # are updated and that the Github check-run is still
        # in-progress.
        self.executor_server.hold_jobs_in_build = True

        # This simulates the typical workflow where a developer only
        # knows the PR id of changes one at a time.
        # The first change:
        A = self.fake_github.openFakePullRequest("gh/project", "master", "A")
        self.fake_github.emitEvent(A.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        # Now that it has been uploaded, upload the second change and
        # point it at the first.
        # B -> A
        B = self.fake_github.openFakePullRequest("gh/project", "master", "B")
        B.body = "{}\n\nDepends-On: {}\n".format(
            B.subject, A.url
        )
        self.fake_github.emitEvent(B.getPullRequestOpenedEvent())
        self.waitUntilSettled()

        # Now that the second change is known, update the first change
        # B <-> A
        A.body = "{}\n\nDepends-On: {}\n".format(
            A.subject, B.url
        )

        self.fake_github.emitEvent(A.getPullRequestEditedEvent(A.subject))
        self.waitUntilSettled()

        # Validate that the Github check-run is still in progress
        # and wasn't cancelled.
        check_runs = self.fake_github.getCommitChecks("gh/project", A.head_sha)
        self.assertEqual(len(check_runs), 1)
        check_run = check_runs[0]
        self.assertEqual(check_run["status"], "in_progress")

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        self.assertHistory([
            dict(name="project-job", result="ABORTED",
                 changes=f"{A.number},{A.head_sha}"),
            dict(name="project-job", result="SUCCESS",
                 changes=f"{A.number},{A.head_sha} {B.number},{B.head_sha}"),
            dict(name="project-job", result="SUCCESS",
                 changes=f"{B.number},{B.head_sha} {A.number},{A.head_sha}"),
        ], ordered=False)
