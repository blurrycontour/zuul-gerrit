#!/usr/bin/env python

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
from collections import defaultdict

import github3.exceptions
import re
import time

import graphene
from requests import HTTPError
from requests.structures import CaseInsensitiveDict

from tests.fake_graphql import FakeGithubQuery

FAKE_BASE_URL = 'https://example.com/api/v3/'


class ErrorResponse:
    status_code = 0
    message = ''

    def json(self):
        return {
            'message': self.message
        }


class FakeUser(object):
    def __init__(self, login):
        self.login = login
        self.name = "Github User"
        self.email = "github.user@example.com"
        self.html_url = 'https://example.com/%s' % login


class FakeBranch(object):
    def __init__(self, fake_repo, branch='master', protected=False):
        self.name = branch
        self._fake_repo = fake_repo

    @property
    def protected(self):
        return self.name in self._fake_repo._branch_protection_rules

    def as_dict(self):
        return {
            'name': self.name,
            'protected': self.protected
        }


class FakeStatus(object):
    def __init__(self, state, url, description, context, user):
        self.state = state
        self.context = context
        self._url = url
        self._description = description
        self._user = user

    def as_dict(self):
        return {
            'state': self.state,
            'url': self._url,
            'description': self._description,
            'context': self.context,
            'creator': {
                'login': self._user
            }
        }


class FakeCheckRun(object):
    def __init__(self, name, details_url, output, status, conclusion,
                 completed_at, external_id, actions, app):
        if actions is None:
            actions = []

        self.name = name
        self.details_url = details_url
        self.output = output
        self.conclusion = conclusion
        self.completed_at = completed_at
        self.external_id = external_id
        self.actions = actions
        self.app = app

        # Github automatically sets the status to "completed" if a conclusion
        # is provided.
        if conclusion is not None:
            self.status = "completed"
        else:
            self.status = status

    def as_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "output": self.output,
            "details_url": self.details_url,
            "conclusion": self.conclusion,
            "completed_at": self.completed_at,
            "external_id": self.external_id,
            "actions": self.actions,
            "app": {
                "slug": self.app,
            },
        }

    def update(self, conclusion, completed_at, output, details_url,
               external_id, actions):
        self.conclusion = conclusion
        self.completed_at = completed_at
        self.output = output
        self.details_url = details_url
        self.external_id = external_id
        self.actions = actions

        # As we are only calling the update method when a build is completed,
        # we can always set the status to "completed".
        self.status = "completed"


class FakeGHReview(object):

    def __init__(self, data):
        self.data = data

    def as_dict(self):
        return self.data


class FakeCombinedStatus(object):
    def __init__(self, sha, statuses):
        self.sha = sha
        self.statuses = statuses


class FakeCommit(object):
    def __init__(self, sha):
        self._statuses = []
        self.sha = sha
        self._check_runs = []

    def set_status(self, state, url, description, context, user):
        status = FakeStatus(
            state, url, description, context, user)
        # always insert a status to the front of the list, to represent
        # the last status provided for a commit.
        self._statuses.insert(0, status)

    def set_check_run(self, name, details_url, output, status, conclusion,
                      completed_at, external_id, actions, app):
        check_run = FakeCheckRun(
            name,
            details_url,
            output,
            status,
            conclusion,
            completed_at,
            external_id,
            actions,
            app,
        )
        # Always insert a check_run to the front of the list to represent the
        # last check_run provided for a commit.
        self._check_runs.insert(0, check_run)

    def get_url(self, path, params=None):
        if path == 'statuses':
            statuses = [s.as_dict() for s in self._statuses]
            return FakeResponse(statuses)
        if path == "check-runs":
            check_runs = [c.as_dict() for c in self._check_runs]
            resp = {"total_count": len(check_runs), "check_runs": check_runs}
            return FakeResponse(resp)

    def statuses(self):
        return self._statuses

    def check_runs(self):
        return self._check_runs

    def status(self):
        '''
        Returns the combined status wich only contains the latest statuses of
        the commit together with some other information that we don't need
        here.
        '''
        latest_statuses_by_context = {}
        for status in self._statuses:
            if status.context not in latest_statuses_by_context:
                latest_statuses_by_context[status.context] = status
        combined_statuses = latest_statuses_by_context.values()
        return FakeCombinedStatus(self.sha, combined_statuses)


class FakeRepository(object):
    def __init__(self, name, data):
        self._api = FAKE_BASE_URL
        self._branches = [FakeBranch(self)]
        self._commits = {}
        self.data = data
        self.name = name

        # Simple dictionary to store permission values per feature (e.g.
        # checks, Repository contents, Pull requests, Commit statuses, ...).
        # Could be used to just enable/deable a permission (True, False) or
        # provide more specific values like "read" or "read&write". The mocked
        # functionality in the FakeRepository class should then check for this
        # value and raise an appropriate exception like a production Github
        # would do in case the permission is not sufficient or missing at all.
        self._permissions = {}

        # List of branch protection rules
        self._branch_protection_rules = defaultdict(FakeBranchProtectionRule)

        # fail the next commit requests with 404
        self.fail_not_found = 0

    def branches(self, protected=False):
        if protected:
            # simulate there is no protected branch
            return [b for b in self._branches if b.protected]
        return self._branches

    def _set_branch_protection(self, branch_name, protected=True,
                               contexts=None):
        if not protected:
            if branch_name in self._branch_protection_rules:
                del self._branch_protection_rules[branch_name]
            return

        rule = self._branch_protection_rules[branch_name]
        rule.pattern = branch_name
        rule.required_contexts = contexts or []

    def _set_permission(self, key, value):
        # NOTE (felix): Currently, this is only used to mock a repo with
        # missing checks API permissions. But we could also use it to test
        # arbitrary permission values like missing write, but only read
        # permissions for a specific functionality.
        self._permissions[key] = value

    def _build_url(self, *args, **kwargs):
        path_args = ['repos', self.name]
        path_args.extend(args)
        fakepath = '/'.join(path_args)
        return FAKE_BASE_URL + fakepath

    def _get(self, url, headers=None):
        client = FakeGithubClient(self.data)
        return client.session.get(url, headers)

    def _create_branch(self, branch):
        self._branches.append((FakeBranch(self, branch=branch)))

    def _delete_branch(self, branch_name):
        self._branches = [b for b in self._branches if b.name != branch_name]

    def create_status(self, sha, state, url, description, context,
                      user='zuul'):
        # Since we're bypassing github API, which would require a user, we
        # default the user as 'zuul' here.
        commit = self._commits.get(sha, None)
        if commit is None:
            commit = FakeCommit(sha)
            self._commits[sha] = commit
        commit.set_status(state, url, description, context, user)

    def create_check_run(self, head_sha, name, details_url=None, output=None,
                         status=None, conclusion=None, completed_at=None,
                         external_id=None, actions=None, app="zuul"):

        # Raise the appropriate github3 exception in case we don't have
        # permission to access the checks API
        if self._permissions.get("checks") is False:
            # To create a proper github3 exception, we need to mock a response
            # object
            raise github3.exceptions.ForbiddenError(
                FakeResponse("Resource not accessible by integration", 403)
            )

        commit = self._commits.get(head_sha, None)
        if commit is None:
            commit = FakeCommit(head_sha)
            self._commits[head_sha] = commit
        commit.set_check_run(
            name,
            details_url,
            output,
            status,
            conclusion,
            completed_at,
            external_id,
            actions,
            app,
        )

    def commit(self, sha):

        if self.fail_not_found > 0:
            self.fail_not_found -= 1

            resp = ErrorResponse()
            resp.status_code = 404
            resp.message = 'Not Found'

            raise github3.exceptions.NotFoundError(resp)

        commit = self._commits.get(sha, None)
        if commit is None:
            commit = FakeCommit(sha)
            self._commits[sha] = commit
        return commit

    def get_url(self, path, params=None):
        if '/' in path:
            entity, request = path.split('/', 1)
        else:
            entity = path
            request = None

        if entity == 'branches':
            return self.get_url_branches(request, params=params)
        if entity == 'collaborators':
            return self.get_url_collaborators(request)
        if entity == 'commits':
            return self.get_url_commits(request, params=params)
        else:
            return None

    def get_url_branches(self, path, params=None):
        if path is None:
            # request wants a branch list
            return self.get_url_branch_list(params)

        elements = path.split('/')

        entity = elements[-1]
        if entity == 'protection':
            branch = '/'.join(elements[0:-1])
            return self.get_url_protection(branch)
        else:
            # fall back to treat all elements as branch
            branch = '/'.join(elements)
            return self.get_url_branch(branch)

    def get_url_commits(self, path, params=None):
        if '/' in path:
            sha, request = path.split('/', 1)
        else:
            sha = path
            request = None
        commit = self._commits.get(sha)

        # Commits are created lazy so check if there is a PR with the correct
        # head sha.
        if commit is None:
            pull_requests = [pr for pr in self.data.pull_requests.values()
                             if pr.head_sha == sha]
            if pull_requests:
                commit = FakeCommit(sha)
                self._commits[sha] = commit

        if not commit:
            return FakeResponse({}, 404)

        return commit.get_url(request, params=params)

    def get_url_branch_list(self, params):
        if params.get('protected') == 1:
            exclude_unprotected = True
        else:
            exclude_unprotected = False
        branches = [x.as_dict() for x in self.branches(exclude_unprotected)]

        return FakeResponse(branches, 200)

    def get_url_branch(self, branch_name):
        for branch in self._branches:
            if branch.name == branch_name:
                return FakeResponse(branch.as_dict())
        return FakeResponse(None, 404)

    def get_url_collaborators(self, path):
        login, entity = path.split('/')

        if entity == 'permission':
            owner, proj = self.name.split('/')
            permission = None
            for pr in self.data.pull_requests.values():
                pr_owner, pr_project = pr.project.split('/')
                if (pr_owner == owner and proj == pr_project):
                    if login in pr.admins:
                        permission = 'admin'
                        break
                    elif login in pr.writers:
                        permission = 'write'
                        break
                    else:
                        permission = 'read'
            data = {
                'permission': permission,
            }
            return FakeResponse(data)
        else:
            return None

    def get_url_protection(self, branch):
        rule = self._branch_protection_rules.get(branch)

        if not rule:
            # Note that GitHub returns 404 if branch protection is off so do
            # the same here as well
            return FakeResponse({}, 404)
        data = {
            'required_status_checks': {
                'contexts': rule.required_contexts
            }
        }
        return FakeResponse(data)

    def pull_requests(self, state=None, sort=None, direction=None):
        # sort and direction are unused currently, but present to match
        # real world call signatures.
        pulls = []
        for pull in self.data.pull_requests.values():
            if pull.project != self.name:
                continue
            if state and pull.state != state:
                continue
            pulls.append(FakePull(pull))
        return pulls


class FakeIssue(object):
    def __init__(self, fake_pull_request):
        self._fake_pull_request = fake_pull_request

    def pull_request(self):
        return FakePull(self._fake_pull_request)

    @property
    def number(self):
        return self._fake_pull_request.number


class FakeFile(object):
    def __init__(self, filename):
        self.filename = filename


class FakePull(object):
    def __init__(self, fake_pull_request):
        self._fake_pull_request = fake_pull_request

    def issue(self):
        return FakeIssue(self._fake_pull_request)

    def files(self):
        # Github lists max. 300 files of a PR in alphabetical order
        return [FakeFile(fn)
                for fn in sorted(self._fake_pull_request.files)][:300]

    def reviews(self):
        return self._fake_pull_request.reviews

    def create_review(self, body, commit_id, event):
        review = FakeGHReview({
            'state': event,
            'user': {
                'login': 'fakezuul',
                'email': 'fakezuul@fake.test',
            },
            'submitted_at': time.gmtime(),
        })
        self._fake_pull_request.reviews.append(review)
        return review

    @property
    def head(self):
        client = FakeGithubClient(self._fake_pull_request.github.github_data)
        repo = client.repo_from_project(self._fake_pull_request.project)
        return repo.commit(self._fake_pull_request.head_sha)

    def commits(self):
        # since we don't know all commits of a pr we just return here a list
        # with the head_sha as the only commit
        return [self.head]

    def merge(self, commit_message=None, sha=None, merge_method=None):
        conn = self._fake_pull_request.github
        pr = self._fake_pull_request

        # record that this got reported
        conn.reports.append((pr.project, pr.number, 'merge', merge_method))
        if conn.merge_failure:
            raise Exception('Unknown merge failure')
        if conn.merge_not_allowed_count > 0:
            conn.merge_not_allowed_count -= 1
            resp = ErrorResponse()
            resp.status_code = 403
            resp.message = 'Merge not allowed'
            raise github3.exceptions.MethodNotAllowed(resp)
        pr.setMerged(commit_message)
        return True

    def as_dict(self):
        pr = self._fake_pull_request
        connection = pr.github
        data = {
            'number': pr.number,
            'title': pr.subject,
            'url': 'https://%s/api/v3/%s/pulls/%s' % (
                connection.server, pr.project, pr.number
            ),
            'html_url': 'https://%s/%s/pull/%s' % (
                connection.server, pr.project, pr.number
            ),
            'updated_at': pr.updated_at,
            'base': {
                'repo': {
                    'full_name': pr.project
                },
                'ref': pr.branch,
            },
            'draft': pr.draft,
            'mergeable': True,
            'state': pr.state,
            'head': {
                'sha': pr.head_sha,
                'ref': pr.getPRReference(),
                'repo': {
                    'full_name': pr.project
                }
            },
            'merged': pr.is_merged,
            'body': pr.body,
            'body_text': pr.body_text,
            'changed_files': len(pr.files),
            'labels': [{'name': l} for l in pr.labels]
        }
        return data


class FakeIssueSearchResult(object):
    def __init__(self, issue):
        self.issue = issue


class FakeResponse(object):
    def __init__(self, data, status_code=200):
        self.status_code = status_code
        self.data = data
        self.links = {}

    @property
    def content(self):
        # Building github3 exceptions requires a Response object with the
        # content attribute set.
        return self.data

    def json(self):
        return self.data

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise HTTPError('{} Something went wrong'.format(self.status_code),
                            response=self)


class FakeGithubSession(object):

    def __init__(self, client):
        self.client = client
        self.headers = CaseInsensitiveDict()
        self._base_url = None
        self.schema = graphene.Schema(query=FakeGithubQuery)

    def build_url(self, *args):
        fakepath = '/'.join(args)
        return FAKE_BASE_URL + fakepath

    def get(self, url, headers=None, params=None):
        request = url
        if request.startswith(FAKE_BASE_URL):
            request = request[len(FAKE_BASE_URL):]

        entity, request = request.split('/', 1)

        if entity == 'repos':
            return self.get_repo(request, params=params)
        else:
            # unknown entity to process
            return None

    def post(self, url, data=None, headers=None, params=None, json=None):

        if json and json.get('query'):
            query = json.get('query')
            variables = json.get('variables')
            result = self.schema.execute(
                query, variables=variables, context=self.client._data)
            return FakeResponse({'data': result.data}, 200)

        return FakeResponse(None, 404)

    def get_repo(self, request, params=None):
        org, project, request = request.split('/', 2)
        project_name = '{}/{}'.format(org, project)

        repo = self.client.repo_from_project(project_name)

        return repo.get_url(request, params=params)


class FakeBranchProtectionRule:

    def __init__(self):
        self.pattern = None
        self.required_contexts = []
        self.require_reviews = False
        self.require_codeowners_review = False


class FakeGithubData(object):
    def __init__(self, pull_requests):
        self.pull_requests = pull_requests
        self.repos = {}


class FakeGithubClient(object):
    def __init__(self, data, inst_id=None):
        self._data = data
        self._inst_id = inst_id
        self.session = FakeGithubSession(self)

    def user(self, login):
        return FakeUser(login)

    def repository(self, owner, proj):
        return self._data.repos.get((owner, proj), None)

    def repo_from_project(self, project):
        # This is a convenience method for the tests.
        owner, proj = project.split('/')
        return self.repository(owner, proj)

    def addProject(self, project):
        owner, proj = project.name.split('/')
        self._data.repos[(owner, proj)] = FakeRepository(
            project.name, self._data)

    def addProjectByName(self, project_name):
        owner, proj = project_name.split('/')
        self._data.repos[(owner, proj)] = FakeRepository(
            project_name, self._data)

    def pull_request(self, owner, project, number):
        fake_pr = self._data.pull_requests[int(number)]
        return FakePull(fake_pr)

    def search_issues(self, query):
        def tokenize(s):
            # Tokenize with handling for quoted substrings.
            # Bit hacky and needs PDA, but our current inputs are
            # constrained enough that this should work.
            s = s[:-len(" type:pr is:open in:body")]
            OR_split = [x.strip() for x in s.split('OR')]
            tokens = [x.strip('"') for x in OR_split]
            return tokens

        def query_is_sha(s):
            return re.match(r'[a-z0-9]{40}', s)

        if query_is_sha(query):
            return (FakeIssueSearchResult(FakeIssue(pr))
                    for pr in self._data.pull_requests.values()
                    if pr.head_sha == query)

        # Non-SHA queries are of the form:
        #
        #     '"Depends-On: <url>" OR "Depends-On: <url>"
        #      OR ... type:pr is:open in:body'
        #
        # For the tests is currently enough to simply check for the
        # existence of the Depends-On strings in the PR body.
        tokens = tokenize(query)
        terms = set(tokens)
        results = []
        for pr in self._data.pull_requests.values():
            if not pr.body:
                body = ""
            else:
                body = pr.body
            for term in terms:
                if term in body:
                    issue = FakeIssue(pr)
                    results.append(FakeIssueSearchResult(issue))
                    break

        return iter(results)
