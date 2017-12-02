# Copyright 2011 OpenStack, LLC.
# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

import git
import time
import logging
import urllib
import threading

import voluptuous as v

from zuul.connection import BaseConnection
from zuul.driver.git.gitmodel import GitTriggerEvent, EMPTY_GIT_REF
from zuul.model import Ref, Branch


class GitWatcher(threading.Thread):
    log = logging.getLogger("connection.git.GitWatcher")

    def __init__(self, git_connection, baseurl, poll_timeout):
        threading.Thread.__init__(self)
        self.daemon = True
        self.git_connection = git_connection
        self.baseurl = baseurl
        self.poll_timeout = poll_timeout
        self._stopped = False
        self.projects_refs = {}

    def ls_remote(self, project):
        refs = {}
        client = git.cmd.Git()
        output = client.ls_remote(self.baseurl + '/' + project)
        for ref in output.splitlines():
            sha, branch = ref.split('\t')
            if branch.startswith('refs/heads/'):
                refs[branch] = sha
        return refs

    def compare_refs(self, project, refs):
        events = []
        # Fetch previous refs state
        base_refs = self.projects_refs.get(project)
        # Create list of created refs
        rcreateds = set(refs.keys()) - set(base_refs.keys())
        # Create list of deleted refs
        rdeleteds = set(base_refs.keys()) - set(refs.keys())
        updateds = {}
        createds = {}
        deleteds = {}
        for ref, sha in refs.items():
            if ref in rcreateds:
                createds[ref] = sha
            elif ref in rdeleteds:
                deleteds[ref] = sha
            else:
                rsha = base_refs[ref]
                if rsha != sha:
                    updateds[ref] = sha
        for created, sha in createds.items():
            self.log.debug("Ref %s created with sha %s" % (created, sha))
            event = GitTriggerEvent()
            event.type = 'ref-created'
            event.project_hostname = self.git_connection.canonical_hostname
            event.project_name = project
            event.branch = created
            event.branch_created = True
            event.ref = created
            event.oldrev = EMPTY_GIT_REF
            event.newrev = sha
            events.append(event)
        for deleted, sha in deleteds.items():
            self.log.debug("Ref %s deleted" % deleted)
            event = GitTriggerEvent()
            event.type = 'ref-deleted'
            event.project_hostname = self.git_connection.canonical_hostname
            event.project_name = project
            event.branch = created
            event.branch_deleted = True
            event.ref = deleted
            event.oldrev = sha
            event.newrev = EMPTY_GIT_REF
            events.append(event)
        for updated, sha in updateds.items():
            self.log.debug("Ref %s updated to %s" % (updated, sha))
            event = GitTriggerEvent()
            event.type = 'ref-updated'
            event.project_hostname = self.git_connection.canonical_hostname
            event.project_name = project
            event.branch = updated
            event.branch_updated = True
            event.ref = updated
            event.oldrev = base_refs[updated]
            event.newrev = sha
            events.append(event)
        return events

    def _run(self):
        self.log.debug("Walk through projects refs for connection: %s" %
                       self.git_connection.connection_name)
        # Read repositories refs and send events to the scheduler
        try:
            for project in self.git_connection.projects:
                self.log.debug("Discover refs for project %s" % project)
                refs = self.ls_remote(project)
                if not self.projects_refs.get(project):
                    # State for this project does not exists yet so add it.
                    # No event will be triggered in this loop as
                    # projects_refs['project'] and refs are equal
                    self.projects_refs[project] = refs
                events = self.compare_refs(project, refs)
                self.projects_refs[project] = refs
                for event in events:
                    self.git_connection.logEvent(event)
                    self.git_connection.sched.addEvent(event)
        except Exception as e:
            self.log.debug("Unexpected issue in _run loop: %s" % str(e))
        # Polling wait delay
        time.sleep(self.poll_timeout)

    def run(self):
        while not self._stopped:
            self._run()

    def stop(self):
        self._stopped = True


class GitConnection(BaseConnection):
    driver_name = 'git'
    log = logging.getLogger("connection.git")

    def __init__(self, driver, connection_name, connection_config):
        super(GitConnection, self).__init__(driver, connection_name,
                                            connection_config)
        if 'baseurl' not in self.connection_config:
            raise Exception('baseurl is required for git connections in '
                            '%s' % self.connection_name)
        self.baseurl = self.connection_config.get('baseurl')
        self.poll_timeout = int(self.connection_config.get('poll_timeout', 10))
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname')
        if not self.canonical_hostname:
            r = urllib.parse.urlparse(self.baseurl)
            if r.hostname:
                self.canonical_hostname = r.hostname
            else:
                self.canonical_hostname = 'localhost'
        self.projects = {}

    def getProject(self, name):
        return self.projects.get(name)

    def addProject(self, project):
        self.projects[project.name] = project

    def getChangeFilesUpdated(self, project_name, branch):
        job = self.sched.merger.getFilesChanges(
            self.connection_name, project_name, branch)
        self.log.debug("Waiting for fileschanges job %s" % job)
        job.wait()
        if not job.updated:
            raise Exception("Fileschanges job %s failed" % job)
        self.log.debug("Fileschanges job %s got changes on files %s" %
                       (job, job.files))
        return job.files

    def getChange(self, event, refresh=False):
        if event.ref and event.ref.startswith('refs/heads/'):
            project = self.getProject(event.project_name)
            change = Branch(project)
            change.ref = event.ref
            change.branch = event.ref[len('refs/heads/'):]
            change.files = self.getChangeFilesUpdated(
                event.project_name, change.branch)
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.url = ""
        elif event.ref:
            # catch-all ref (ie, not a branch or head)
            project = self.getProject(event.project_name)
            change = Ref(project)
            change.ref = event.ref
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.url = ""
        else:
            self.log.warning("Unable to get change for %s" % (event,))
            change = None
        return change

    def getProjectBranches(self, project, tenant):
        # TODO(jeblair): implement; this will need to handle local or
        # remote git urls.
        return ['master']

    def getGitUrl(self, project):
        url = '%s/%s' % (self.baseurl, project.name)
        return url

    def onLoad(self):
        self.log.debug("Starting Git Watcher")
        self._start_watcher_thread()

    def onStop(self):
        self.log.debug("Stopping Git Watcher")
        self._stop_watcher_thread()

    def _stop_watcher_thread(self):
        if self.watcher_thread:
            self.watcher_thread.stop()
            self.watcher_thread.join()

    def _start_watcher_thread(self):
        self.watcher_thread = GitWatcher(
            self,
            self.baseurl,
            self.poll_timeout)
        self.watcher_thread.start()


def getSchema():
    git_connection = v.Any(str, v.Schema(dict))
    return git_connection
