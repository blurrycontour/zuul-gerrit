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
from typing import Iterable

import github3.exceptions
import re
import time

import graphene
from requests import HTTPError
from uritemplate import URITemplate

from tests.fake_graphql import FakeGithubQuery

FAKE_BASE_URL = 'https://example.com/api/v3/'


class FakeUser(object):
    def __init__(self, login):
        self.login = login
        self.name = "Github User"
        self.email = "github.user@example.com"
        self.html_url = 'https://example.com/%s' % login


class FakeBranch(object):
    def __init__(self, branch='master', protected=False):
        self.name = branch
        self.protected = protected
        self.require_codeowners = False

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

    def set_status(self, state, url, description, context, user):
        status = FakeStatus(
            state, url, description, context, user)
        # always insert a status to the front of the list, to represent
        # the last status provided for a commit.
        self._statuses.insert(0, status)

    def get_url(self, path, params=None):
        if path == 'statuses':
            statuses = [s.as_dict() for s in self._statuses]
            return FakeResponse(statuses)

    def statuses(self):
        return self._statuses

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
        self._branches = [FakeBranch()]
        self._commits = {}
        self.data = data
        self.name = name
        self._teams = []
        self._collaborators = []

        # fail the next commit requests with 404
        self.fail_not_found = 0

    def branches(self, protected=False):
        if protected:
            # simulate there is no protected branch
            return [b for b in self._branches if b.protected]
        return self._branches

    def _set_branch_protection(self,
                               branch_name,
                               protected,
                               require_codeowners=False):
        for branch in self._branches:
            if branch.name == branch_name:
                branch.protected = protected
                branch.require_codeowners = require_codeowners
                return

    def _build_url(self, *args, **kwargs):
        path_args = ['repos', self.name]
        path_args.extend(args)
        fakepath = '/'.join(path_args)
        return FAKE_BASE_URL + fakepath

    def _get(self, url, headers=None):
        client = FakeGithubClient(self.data)
        return client.session.get(url, headers)

    def _create_branch(self, branch):
        self._branches.append((FakeBranch(branch=branch)))

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

    def commit(self, sha):

        if self.fail_not_found > 0:
            self.fail_not_found -= 1

            class Response:
                status_code = 0
                message = ''

                def json(self):
                    return {
                        'message': self.message
                    }

            resp = Response()
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
        fake_branch = next((b for b in self._branches if b.name == branch),
                           None)
        if fake_branch is not None and fake_branch.protected:
            data = {
                'required_status_checks': {},
                'required_pull_request_reviews': {
                    'require_code_owner_reviews':
                        fake_branch.require_codeowners
                }
            }

            contexts = self.data.required_contexts.get((self.name, branch), [])
            if contexts is not None:
                data['required_status_checks']['contexts'] = contexts

            return FakeResponse(data)
        else:
            # Note that GitHub returns 404 if branch protection is off so do
            # the same here as well
            return FakeResponse({}, 404)

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

    def teams(self):
        # ensure that every team has a session
        session = FakeGithubClient(self.data).session
        for team in self._teams:
            if not team.session:
                team.session = session
        return self._teams

    def collaborators(self):
        return self._collaborators


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

    def as_dict(self):
        pr = self._fake_pull_request
        connection = pr.github
        data = {
            'number': pr.number,
            'title': pr.subject,
            'url': 'https://%s/%s/pull/%s' % (
                connection.server, pr.project, pr.number
            ),
            'updated_at': pr.updated_at,
            'base': {
                'repo': {
                    'full_name': pr.project
                },
                'ref': pr.branch,
            },
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

    def json(self):
        return self.data

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise HTTPError('{} Something went wrong'.format(self.status_code),
                            response=self)


class FakeGithubSession(object):

    def __init__(self, data):
        self._data = data
        self._base_url = None
        self._prepared_responses = {}
        self.schema = graphene.Schema(query=FakeGithubQuery)

    def build_url(self, *args, **kwargs):
        self._base_url = kwargs.get("base_url")
        fakepath = '/'.join(args)
        return FAKE_BASE_URL + fakepath

    def get(self, url, headers=None, params=None):
        request = url
        if request.startswith(FAKE_BASE_URL):
            request = request[len(FAKE_BASE_URL):]

        entity, request = request.split('/', 1)

        if entity == 'repos':
            return self.get_repo(request, params=params)
        elif entity == 'teams':
            return self.get_team(request, params=params)
        else:
            # unknown entity to process
            return None

    def post(self, url, data=None, headers=None, params=None, json=None):

        if json and json.get('query'):
            query = json.get('query')
            result = self.schema.execute(query, context=self._data)
            return FakeResponse({'data': result.data}, 200)

        return FakeResponse(None, 404)

    def get_repo(self, request, params=None):
        org, project, request = request.split('/', 2)
        project_name = '{}/{}'.format(org, project)

        client = FakeGithubClient(self._data)
        repo = client.repo_from_project(project_name)

        return repo.get_url(request, params=params)

    def get_team(self, request, params=None):
        slug, request = request.split('/', 1)
        teams = [team
                 for org in self._data.organizations.values()
                 for team in org.fake_teams
                 if team.slug == slug]
        if not teams:
            return FakeResponse({}, 404)
        team = teams[0]

        return team.get_url(request, params)

    def add_fake_response(self, method, url_regex, response):
        if method not in self._prepared_responses:
            self._prepared_responses[method] = {}
        self._prepared_responses[method][url_regex] = response


class FakeGithubData(object):
    def __init__(self, pull_requests):
        self.pull_requests = pull_requests
        self.repos = {}
        self.required_contexts = {}
        self.organizations = {}


class FakeGithubTeamMember(object):
    def __init__(self, name):
        self.login = name


class FakeGithubTeam(object):
    def __init__(self, name, slug=None, members=None, permission='pull'):
        if members is not None:
            self._members = dict((name, FakeGithubTeamMember(name))
                                 for name in members)
        else:
            self._members = dict()
        self.name = name
        if slug:
            self.slug = slug
        else:
            self.slug = name
        self.permission = permission
        self.session = None

    def is_member(self, username: str) -> bool:
        return username in self._members

    def members(self) -> Iterable[FakeGithubTeamMember]:
        return self._members.values()

    @property
    def members_urlt(self):
        return URITemplate(FAKE_BASE_URL + 'teams/' + self.slug +
                           '/members{/member}')

    def get_url(self, request, params=None):
        if request != 'members':
            # not implemented
            return FakeResponse({}, 404)

        result = [{'login': member for member in self._members}]
        return FakeResponse(result)


class FakeGithubCollaborator(object):
    def __init__(self, login, permissions=None):
        if permissions is None:
            permissions = dict()
        self.login = login
        self.permissions = permissions


class FakeGithubOrganization(object):
    def __init__(self, fake_teams=None):
        if fake_teams is None:
            fake_teams = []
        self.fake_teams = fake_teams

    def teams(self):
        return iter(self.fake_teams)


class FakeGithubClient(object):
    def __init__(self, data, inst_id=None):
        self._data = data
        self._inst_id = inst_id
        self.session = FakeGithubSession(data)

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
            return re.findall(r'[\w]+', s)

        def query_is_sha(s):
            return re.match(r'[a-z0-9]{40}', s)

        if query_is_sha(query):
            return (FakeIssueSearchResult(FakeIssue(pr))
                    for pr in self._data.pull_requests.values()
                    if pr.head_sha == query)

        parts = tokenize(query)
        terms = set()
        results = []
        for part in parts:
            kv = part.split(':', 1)
            if len(kv) == 2:
                if kv[0] in set('type', 'is', 'in'):
                    # We only perform one search now and these aren't
                    # important; we can honor these terms later if
                    # necessary.
                    continue
            terms.add(part)

        for pr in self._data.pull_requests.values():
            if not pr.body:
                body = set()
            else:
                body = set(tokenize(pr.body))
            if terms.intersection(body):
                issue = FakeIssue(pr)
                results.append(FakeIssueSearchResult(issue))

        return iter(results)

    def organization(self, org_name):
        return self._data.organizations.get(org_name, None)
