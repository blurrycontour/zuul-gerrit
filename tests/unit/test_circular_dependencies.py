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

import textwrap

from tests.base import ZuulTestCase


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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

        A.addApproval("Code-Review", 2)
        B.addApproval("Code-Review", 2)
        B.addApproval("Approved", 1)
        self.fake_gerrit.addEvent(A.addApproval("Approved", 1))
        self.waitUntilSettled()

        self.assertEqual(A.reported, 3)
        self.assertEqual(B.reported, 2)
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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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
        self.assertIn("bundle that is failing.", B.messages[-1])
        self.assertIn("bundle that is failing.", C.messages[-1])
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
        for connection in self.connections.connections.values():
            connection.maintainCache([])

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

    def test_cycle_larger_pipeline_window(self):
        tenant = self.sched.abide.tenants.get("tenant-one")

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

        self.assertEqual(A.reported, 2)
        self.assertEqual(B.reported, 3)
        self.assertEqual(A.patchsets[-1]["approvals"][-1]["value"], "-2")
        self.assertEqual(B.patchsets[-1]["approvals"][-1]["value"], "-2")
        self.assertIn("bundle", A.messages[-1])
        self.assertIn("bundle", B.messages[-1])
        self.assertEqual(A.data["status"], "NEW")
        self.assertEqual(B.data["status"], "NEW")

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

        self.assertEqual(len(self.builds), 2)
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

        tenant = self.sched.abide.tenants.get("tenant-one")
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
        self.gearman_server.hold_merge_jobs_in_queue = True
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
        tenant = self.sched.abide.tenants.get('tenant-one')
        items = tenant.layout.pipelines['gate'].getAllItems()
        builds = items[0].current_build_set.unable_to_merge = True

        self.waitUntilSettled()

        self.gearman_server.hold_merge_jobs_in_queue = False
        self.gearman_server.release()
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
                check:
                  jobs:
                    - new-job
                gate:
                  queue: integrated
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


class TestGithubCircularDependencies(ZuulTestCase):
    config_file = "zuul-gerrit-github.conf"
    tenant_config_file = "config/circular-dependencies/main.yaml"

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


class TestCrossSourceCircularDependencies(ZuulTestCase):
    config_file = "zuul-gerrit-github.conf"
    tenant_config_file = "config/circular-dependencies/main.yaml"

    # TODO(swestphahl): add test cases
