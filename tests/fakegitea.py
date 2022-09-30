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
import json
import logging
import os
import re
import requests
import time

import git

import zuul.driver.gitea.giteaconnection as giteaconnection


class GiteaChangeReference(git.Reference):
    _common_path_default = "refs/pull"
    _points_to_commits_only = True


class FakeGiteaConnection(giteaconnection.GiteaConnection):
    """A Fake Gitea connection for use in tests.

    This subclasses
    :py:class:`~zuul.connection.gitea.GiteaConnection` to add the
    ability for tests to add changes to the fake Gitea it represents.
    """

    log = logging.getLogger("zuul.test.FakeGiteaConnection")

    def __init__(self, driver, connection_name, connection_config,
                 changes_db=None, upstream_root=None):
        super(FakeGiteaConnection, self).__init__(
            driver, connection_name, connection_config)
        self.connection_name = connection_name
        self.pr_number = 0
        self.pull_requests = changes_db
        self.statuses = {}
        self.upstream_root = upstream_root

    def setZuulWebPort(self, port):
        self.zuul_web_port = port

    def get_project_api_client(self, project):
        client = FakeGiteaAPIClient(
            self.baseurl, None, project,
            pull_requests_db=self.pull_requests,
            statuses_db=self.statuses)
        return client

    def getGitUrl(self, project):
        return 'file://' + os.path.join(self.upstream_root, project.name)

    def emitEvent(self, event, use_zuulweb=False, project=None,
                  wrong_token=False):
        name, subtype, data = event
        payload = json.dumps(data).encode('utf8')
        secret = self.connection_config['webhook_secret']
        signature = giteaconnection._sign_request(payload, secret)
        headers = {'x-gitea-signature': signature,
                   'x-gitea-event': name}
        if subtype:
            headers['x-gitea-event-type'] = subtype
        if use_zuulweb:
            return requests.post(
                'http://127.0.0.1:%s/api/connection/%s/payload'
                % (self.zuul_web_port, self.connection_name),
                data=payload, headers=headers)
        else:
            data = {'headers': headers, 'payload': data}
            self.event_queue.put(data)
            return data

    def openFakePullRequest(self, project, branch, subject, files=[],
                            initial_comment=None):
        self.pr_number += 1
        pull_request = FakePullRequest(
            self, self.pr_number, project, branch,
            subject, self.upstream_root,
            files=files, initial_comment=initial_comment)
        self.pull_requests.setdefault(
            project, {})[str(self.pr_number)] = pull_request
        return pull_request

    def getGitPushEvent(self, project):
        name = 'push'
        repo_path = os.path.join(self.upstream_root, project)
        repo = git.Repo(repo_path)
        headsha = repo.head.commit.hexsha
        data = {
            'ref': 'refs/heads/master',
            'before': '1' * 40,
            'after': headsha,
            'commits': [],
            'repository': {'full_name': project},
        }
        return (name, 'push', data)

    def getGitBranchEvent(self, project, branch, type, rev):
        name = type
        data = {
            'ref': branch,
            'ref_type': 'branch',
            'sha': rev,
            'repository': {'full_name': project},
        }
        return (name, type, data)


class FakeGiteaAPIClient(giteaconnection.GiteaAPIClient):
    log = logging.getLogger("zuul.test.FakeGiteaAPIClient")

    def __init__(self, baseurl, api_token, project,
                 pull_requests_db=None, statuses_db=None):
        super(FakeGiteaAPIClient, self).__init__(
            baseurl, api_token, project)
        self.session = None
        self.pull_requests = pull_requests_db
        self.statuses = statuses_db
        self.return_post_error = None

    def gen_error(self, verb, custom_only=False):
        if verb == 'POST' and self.return_post_error:
            return {
                'error': self.return_post_error['error'],
                'error_code': self.return_post_error['error_code']
            }, 401, "", 'POST'
            self.return_post_error = None
        if not custom_only:
            return {
                'error': 'some error',
                'error_code': 'some error code'
            }, 503, "", verb

    def _get_pr(self, match):
        project, number = match.groups()
        pr = self.pull_requests.get(project, {}).get(number)
        if not pr:
            return {}, 404, "", 'GET'
        return pr

    def get(self, url, params=None):
        self.log.debug("Getting resource %s ..." % url)

        match = re.match(r'.+/api/v1/repos/(.+)/pulls/(\d+)$', url)
        if match:
            pr = self._get_pr(match)
            if isinstance(pr, tuple):
                # Got error
                return pr
            self.log.error(f"PR = {pr}")
            return {
                'number': pr.number,
                'body': pr.body,
                'title': pr.subject,
                'state': pr.state,
                'updated_at': pr.last_updated,
                'comments': len(pr.comments),
                'mergeable': True,
                'merged': pr.is_merged,
                'base': {
                    'ref': pr.branch,
                    'repo': {'full_name': pr.project},
                },
                'head': {
                    'sha': pr.head_sha,
                    'repo': {'full_name': pr.project},
                },
                'html_url': f'https://fakegitea.com/'
                            f'{pr.project}/pulls/{pr.number}',
                'user': {
                    'login': 'test_user'
                },
                'labels': [{'name': x} for x in pr.labels],
            }, 200, "", "GET"

        match = re.match('.+/api/v1/repos/(.+)/branches/(.+)$', url)
        if match:
            branch = {
                "name": match.group(2),
                "commit": {
                },
                "protected": True,
                "required_approvals": 1,
                "enable_status_check": False,
                "status_check_contexts": None,
                "user_can_push": False,
                "user_can_merge": True,
                "effective_branch_protection_name": ""
            }

            return branch, 200, "", "GET"

        match = re.match(r'.+/api/v1/repos/issues/search$', url)
        if match:
            return [{
                'number': '2',
                'body': 'fake',
                'title': 'Depends-On: '
                         'https://fakegitea.com/org/project/issues/1',
                'state': 'open',
                'repository': {
                    'full_name': 'org/project',
                },
            }], 200, "", "GET"

        return {}, 404, "", "GET"

    def list(self, url, params=None):
        self.log.debug("Listing resource %s ..." % url)

        match = re.match('.+/api/v1/repos/(.+)/branches$', url)
        if match:
            return [{'name': 'master', 'protected': True}]

        match = re.match(r'.+/api/v1/repos/issues/search$', url)
        if match:
            return [{
                'number': '2',
                'body': 'fake',
                'title': 'Depends-On: '
                         'https://fakegitea.com/org/project/issues/1',
                'state': 'open',
                'repository': {
                    'full_name': 'org/project',
                },
            }]

        match = re.match(r'.+/api/v1/repos/(.+)/pulls/(\d+)/reviews$', url)
        if match:
            pr = self._get_pr(match)
            if isinstance(pr, tuple):
                # Got error
                return pr
            self.log.error(f"PR = {pr}")
            return pr.reviews

        return []

    def post(self, url, params=None):

        self.log.info(
            "Posting on resource %s, params (%s) ..." % (url, params))

        # Will only match if return_post_error is set
        err = self.gen_error("POST", custom_only=True)
        if err:
            return err

        match = re.match(r'.+/api/v1/repos/(.+)/issues/(.+)/comments$', url)
        if match:
            pr = self._get_pr(match)
            pr.addComment(params['body'])
            return {}, 200, "", "POST"

        match = re.match(r'.+/api/v1/repos/(.+)/statuses/(.+)$', url)
        if match:
            sha = match.group(2)
            if sha == 'None':
                return {}, 500, "", "POST"
            status = self.statuses.setdefault(sha, dict())
            status[params['state']] = dict(
                context=params.get('context')
            )
            self.statuses[sha] = status
            return {}, 200, "", "POST"

        match = re.match(r'.+/api/v1/repos/(.+)/pulls/(.+)/merge$', url)
        if match:
            pr = self._get_pr(match)
            pr.status = 'closed'
            pr.is_merged = True
            pr.merge_mode = params.get('Do')
            pr.merge_title = params.get('MergeTitleField')
            pr.merge_message = params.get('MergeMessageField')
            return {}, 200, "", "POST"

        return '', 404, "", "POST"


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
        self.state = 'open'
        self.body = initial_comment
        self.comments = []
        self.files = {}
        self.labels = []
        self.sha = None
        self.head_sha = self.sha
        self.upstream_root = upstream_root
        self.url = "https://%s/%s/pulls/%s" % (
            self.gitea.server, self.project, self.number)
        self.pr_ref = self._createPRRef()
        self.is_merged = False
        self.merge_mode = None
        self.merge_title = None
        self.merge_message = None
        self.reviews = []
        self._addCommitToRepo(files=files)
        self._updateTimeStamp()

    def _getPullRequestEvent(self, action, changes=None):
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
                'mergeable': True,
                'state': self.state,
                'title': self.subject,
                'body': self.body,
                'sha': self.sha,
                'updated_at': self.last_updated,
            },
            'repository': {
                'full_name': self.project,
            },
            'sender': {
                'login': 'fake_zuul_user'
            },
            'labels': [
                {'name': x} for x in self.labels
            ],
        }
        if action == 'edited':
            if changes:
                data['changes'] = changes
        return (name, 'pull_request', data)

    def _getIssueCommentEvent(self, action, body):
        name = 'issue_comment'
        data = {
            'action': action,
            'issue': {
                'number': self.number,
                'title': self.subject,
                'updated_at': self.last_updated,
            },
            'repository': {
                'full_name': self.project,
            },
            'comment': {
                'body': body,
            },
            'sender': {
                'login': 'fake_zuul_user'
            },
            'is_pull': True,
        }
        return (name, 'pull_request_comment', data)

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

    def closePullRequest(self):
        self.state = 'closed'
        self._updateTimeStamp()

    def mergePullRequest(self):
        self.state = 'closed'
        self.is_merged = True
        self._updateTimeStamp()

    def reopenPullRequest(self):
        self.state = 'open'
        self.is_merged = False
        self._updateTimeStamp()

    def addReview(self, state='APPROVED', official=True):
        self.reviews.append({
            'state': state,
            'official': official,
            'user': {'full_name': 'tester', 'email': 'fake_mail'},
        })

    def addCommit(self, files={}, delete_files=None):
        """Adds a commit on top of the actual PR head."""
        self._addCommitToRepo(files=files, delete_files=delete_files)
        self._updateTimeStamp()

    def getPRHeadSha(self):
        repo = self._getRepo()
        return repo.references[self.getPRReference()].commit.hexsha

    def getPRReference(self):
        return '%s/head' % self.number

    def getPullRequestOpenedEvent(self):
        return self._getPullRequestEvent('opened')

    def getPullRequestReopenedEvent(self):
        return self._getPullRequestEvent('reopened')

    def getPullRequestClosedEvent(self):
        return self._getPullRequestEvent('closed')

    def getPullRequestUpdatedEvent(self):
        self._addCommitToRepo()
        # self._updateTimeStamp()

        return self._getPullRequestEvent('synchronized')

    def getPullRequestEditedEvent(self, changes=None):
        return self._getPullRequestEvent('edited', changes=changes)

    def addComment(self, message):
        self.comments.append(message)
        self._updateTimeStamp()

    def getPullRequestCommentCreatedEvent(self, comment):
        return self._getIssueCommentEvent('created', comment)

    def getPullRequestCommentDeletedEvent(self, comment):
        return self._getIssueCommentEvent('deleted', comment)

    def getPullRequestInitialCommentEvent(self, comment):
        return self._getPullRequestEvent('edited')

    def getPullRequestLabelUpdatedEvent(self):
        return self._getPullRequestEvent('label_updated')

    def getPullRequestReviewApprovedEvent(self, review):
        (_, _, data) = self._getPullRequestEvent('reviewed')
        data['review'] = dict(
            content=review
        )
        return (
            'pull_request_approved',
            'pull_request_review_approved',
            data
        )

    def getPullRequestReviewRejectedEvent(self, review):
        (_, _, data) = self._getPullRequestEvent('reviewed')
        data['review'] = dict(
            content=review
        )
        return (
            'pull_request_rejected',
            'pull_request_review_rejected',
            data
        )

    def getPullRequestReviewCommentEvent(self, review):
        (_, _, data) = self._getPullRequestEvent('reviewed')
        data['review'] = dict(
            content=review,
        )
        return (
            'issue_comment',
            'pull_request_comment',
            data
        )
