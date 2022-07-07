#!/usr/bin/env python

# Copyright 2022 Open Telekom Cloud, T-Systems International GmbH
# Copyright 2018 Red Hat, Inc.
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
import logging
import os
import time

import git


class GiteaChangeReference(git.Reference):
    _common_path_default = "refs/pull"
    _points_to_commits_only = True


class FakePullRequest(object):
    log = logging.getLogger("zuul.test.FakeGiteaPullRequest")

    def __init__(
        self, gitea, number, project, branch,
        subject, upstream_root, files={}, number_of_commits=1,
        initial_comment=None
    ):
        self.gitea = gitea
        self.source = gitea
        self.number = number
        self.project = project
        self.branch = branch
        self.subject = subject
        self.upstream_root = upstream_root
        self.number_of_commits = 0
        self.status = 'open'
        self.body = initial_comment
        self.comments = []
        self.files = {}
        self.sha = None
        self.head_sha = self.sha
        self.upstream_root = upstream_root
        self.url = "https://%s/%s/pulls/%s" % (
            self.gitea.server, self.project, self.number)
        self.pr_ref = self._createPRRef()
        self._addCommitToRepo(files=files)
        self._updateTimeStamp()

    def _getPullRequestEvent(self, action):
        name = 'pull_request'
        data = {
            'action': action,
            'pull_request': {
                'comments': len(self.comments),
                'number': self.number,
                'base': {
                    'ref': self.branch,
                    'repo': {
                        'full_name': self.project
                    }
                },
                'head': {
                    'sha': self.head_sha,
                    'repo': {
                        'full_name': self.project
                    }
                },
                'status': self.status,
                'title': self.subject,
                'body': self.body,
                'sha': self.sha,
            },
            'repository': {
                'full_name': self.project,
            },
            'sender': {
                'login': 'fake_zuul_user'
            }
        }
        return (name, data)

    def _getRepo(self):
        repo_path = os.path.join(self.upstream_root, self.project)
        return git.Repo(repo_path)

    def _createPRRef(self):
        repo = self._getRepo()
        return GiteaChangeReference.create(
            repo, self.getPRReference(), 'refs/tags/init')

    def _addCommitToRepo(self, files=None, delete_files=None, reset=False):
        repo = self._getRepo()
        ref = repo.references[self.getPRReference()]
        if reset:
            self.number_of_commits = 0
            ref.set_object('refs/tags/init')
        self.number_of_commits += 1
        repo.head.reference = ref
        repo.git.clean('-x', '-f', '-d')

        if files:
            self.files = files
        elif not delete_files:
            fn = '%s-%s' % (self.branch.replace('/', '_'), self.number)
            self.files = {fn: "test %s %s\n" % (self.branch, self.number)}
        msg = self.subject + '-' + str(self.number_of_commits)
        for fn, content in self.files.items():
            fn = os.path.join(repo.working_dir, fn)
            with open(fn, 'w') as f:
                f.write(content)
            repo.index.add([fn])

        if delete_files:
            for fn in delete_files:
                if fn in self.files:
                    del self.files[fn]
                fn = os.path.join(repo.working_dir, fn)
                repo.index.remove([fn])

        self.head_sha = repo.index.commit(msg).hexsha

        repo.create_head(self.getPRReference(), self.head_sha, force=True)
        self.pr_ref.set_commit(self.head_sha)
        repo.head.reference = 'master'
        repo.git.clean('-x', '-f', '-d')
        repo.heads['master'].checkout()

    def _updateTimeStamp(self):
        self.last_updated = str(int(time.time()))

    def getPRHeadSha(self):
        repo = self._getRepo()
        return repo.references[self.getPRReference()].commit.hexsha

    def getPRReference(self):
        return '%s/head' % self.number

    def getPullRequestOpenedEvent(self):
        return self._getPullRequestEvent('opened')
