# Copyright 2020 BMW Group
# Copyright 2024 Acme Gating, LLC
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

import importlib.resources
import logging

from zuul.lib.logutil import get_annotated_logger


def nested_get(d, *keys, default=None):
    temp = d
    for key in keys[:-1]:
        temp = temp.get(key, {}) if temp is not None else None
    return temp.get(keys[-1], default) if temp is not None else default


class GraphQLClient:
    log = logging.getLogger('zuul.github.graphql')

    def __init__(self, url):
        self.url = url
        self.queries = {}
        self._load_queries()

    def _load_queries(self):
        self.log.debug('Loading prepared graphql queries')
        query_names = [
            'canmerge',
            'canmerge-legacy',
            'branch-protection',
            'branch-protection-inner',
        ]
        for query_name in query_names:
            f = importlib.resources.files('zuul').joinpath(
                'driver/github/graphql/%s.graphql' % query_name)
            self.queries[query_name] = f.read_bytes().decode()

    @staticmethod
    def _prepare_query(query, variables):
        data = {
            'query': query,
            'variables': variables,
        }
        return data

    def _run_query(self, log, github, query_name, **args):
        args['zuul_query'] = query_name  # used for logging
        query = self.queries[query_name]
        query = self._prepare_query(query, args)
        response = github.session.post(self.url, json=query)
        response = response.json()
        if 'data' not in response:
            log.error("Error running query %s: %s",
                      query_name, response)
        return response

    def _fetch_canmerge(self, log, github, owner, repo, pull, sha):
        if github.version and github.version[:2] < (2, 21):
            # Github Enterprise prior to 2.21 doesn't offer the review decision
            # so don't request it as this will result in an error.
            query = 'canmerge-legacy'
        else:
            # Since GitHub Enterprise 2.21 and on github.com we can request the
            # review decision state of the pull request.
            query = 'canmerge'
        return self._run_query(log, github, query,
                               owner=owner,
                               repo=repo,
                               pull=pull,
                               head_sha=sha)

    def fetch_canmerge(self, github, change, zuul_event_id=None):
        log = get_annotated_logger(self.log, zuul_event_id)
        owner, repo = change.project.name.split('/')

        data = self._fetch_canmerge(log, github, owner, repo, change.number,
                                    change.patchset)
        result = {}

        repository = nested_get(data, 'data', 'repository')
        # Find corresponding rule to our branch
        rules = nested_get(repository, 'branchProtectionRules', 'nodes',
                           default=[])

        # Filter branch protection rules for the one matching the change.
        matching_rules = [
            rule for rule in rules
            for ref in nested_get(rule, 'matchingRefs', 'nodes', default=[])
            if ref.get('name') == change.branch
        ]
        if len(matching_rules) > 1:
            log.warn('More than one branch protection rules match change %s',
                     change)
            return result
        elif len(matching_rules) == 1:
            matching_rule = matching_rules[0]
        else:
            matching_rule = None

        # If there is a matching rule, get required status checks
        if matching_rule:
            result['requiredStatusCheckContexts'] = matching_rule.get(
                'requiredStatusCheckContexts', [])
            result['requiresApprovingReviews'] = matching_rule.get(
                'requiresApprovingReviews')
            result['requiresCodeOwnerReviews'] = matching_rule.get(
                'requiresCodeOwnerReviews')
            result['protected'] = True
        else:
            result['requiredStatusCheckContexts'] = []
            result['protected'] = False

        # Check for draft
        pull_request = nested_get(repository, 'pullRequest')
        result['isDraft'] = nested_get(pull_request, 'isDraft', default=False)

        # Check if Github detected a merge conflict. Possible enum values
        # are CONFLICTING, MERGEABLE and UNKNOWN.
        result['mergeable'] = nested_get(pull_request, 'mergeable',
                                         default='MERGEABLE')

        # Get review decision. This is supported since GHE 2.21. Default to
        # None to signal if the field is not present.
        result['reviewDecision'] = nested_get(
            pull_request, 'reviewDecision', default=None)

        # Add status checks
        result['status'] = {}
        commit = nested_get(data, 'data', 'repository', 'object')
        # Status can be explicit None so make sure we work with a dict
        # afterwards
        status = commit.get('status') or {}
        for context in status.get('contexts', []):
            result['status'][context['context']] = context

        # Add check runs
        result['checks'] = {}
        for suite in nested_get(commit, 'checkSuites', 'nodes', default=[]):
            for run in nested_get(suite, 'checkRuns', 'nodes', default=[]):
                result['checks'][run['name']] = {
                    **run,
                    "app": suite.get("app")
                }

        return result

    def _fetch_branch_protection(self, log, github, project,
                                 zuul_event_id=None):
        owner, repo = project.name.split('/')
        branches = {}
        branch_subqueries = []

        cursor = None
        while True:
            data = self._run_query(
                log, github, 'branch-protection',
                owner=owner,
                repo=repo,
                cursor=cursor)['data']

            for rule in data['repository']['branchProtectionRules']['nodes']:
                for branch in rule['matchingRefs']['nodes']:
                    branches[branch['name']] = rule['lockBranch']
                refs_pageinfo = rule['matchingRefs']['pageInfo']
                if refs_pageinfo['hasNextPage']:
                    branch_subqueries.append(dict(
                        rule_node_id=rule['id'],
                        cursor=refs_pageinfo['endCursor']))

            rules_pageinfo = data['repository']['branchProtectionRules'
                                                ]['pageInfo']
            if not rules_pageinfo['hasNextPage']:
                break
            cursor = rules_pageinfo['endCursor']

        for subquery in branch_subqueries:
            cursor = subquery['cursor']
            while True:
                data = self._run_query(
                    log, github, 'branch-protection-inner',
                    rule_node_id=subquery['rule_node_id'],
                    cursor=cursor)['data']
                for branch in data['node']['matchingRefs']['nodes']:
                    branches[branch['name']] = rule['lockBranch']
                refs_pageinfo = data['node']['matchingRefs']['pageInfo']
                if not refs_pageinfo['hasNextPage']:
                    break
                cursor = refs_pageinfo['endCursor']
        return branches

    def fetch_branch_protection(self, github, project, zuul_event_id=None):
        """Return a dictionary of branches and whether they are locked"""
        log = get_annotated_logger(self.log, zuul_event_id)
        return self._fetch_branch_protection(log, github, project,
                                             zuul_event_id)
