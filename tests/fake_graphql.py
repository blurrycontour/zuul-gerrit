# Copyright 2019 BMW Group
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

from graphene import Boolean, Field, Int, List, ObjectType, String, Schema


class ID(String):
    """Github global object ids are strings"""
    pass


class PageInfo(ObjectType):
    end_cursor = String()
    has_previous_page = Boolean()
    has_next_page = Boolean()

    def resolve_end_cursor(parent, info):
        return str(parent['after'] + parent['first'])

    def resolve_has_previous_page(parent, info):
        return parent['after'] > 0

    def resolve_has_next_page(parent, info):
        return parent['after'] + parent['first'] < parent['length']


class MatchingRef(ObjectType):
    name = String()

    def resolve_name(parent, info):
        return parent


class MatchingRefs(ObjectType):
    pageInfo = Field(PageInfo)
    nodes = List(MatchingRef)

    def resolve_nodes(parent, info):
        return parent['nodes']

    def resolve_pageInfo(parent, info):
        return parent


class BranchProtectionRule(ObjectType):
    id = ID()
    pattern = String()
    requiredStatusCheckContexts = List(String)
    requiresApprovingReviews = Boolean()
    requiresCodeOwnerReviews = Boolean()
    matchingRefs = Field(MatchingRefs, first=Int(), after=String())
    lockBranch = Boolean()

    def resolve_id(parent, info):
        return parent.id

    def resolve_pattern(parent, info):
        return parent.pattern

    def resolve_requiredStatusCheckContexts(parent, info):
        return parent.required_contexts

    def resolve_requiresApprovingReviews(parent, info):
        return parent.require_reviews

    def resolve_requiresCodeOwnerReviews(parent, info):
        return parent.require_codeowners_review

    def resolve_lockBranch(parent, info):
        return parent.lock_branch

    def resolve_matchingRefs(parent, info, first, after=None):
        if after is None:
            after = '0'
        after = int(after)
        values = parent.matching_refs
        return dict(
            length=len(values),
            nodes=values[after:after + first],
            first=first,
            after=after,
        )


class BranchProtectionRules(ObjectType):
    pageInfo = Field(PageInfo)
    nodes = List(BranchProtectionRule)

    def resolve_nodes(parent, info):
        return parent['nodes']

    def resolve_pageInfo(parent, info):
        return parent


class Actor(ObjectType):
    login = String()


class StatusContext(ObjectType):
    state = String()
    context = String()
    creator = Field(Actor)

    def resolve_state(parent, info):
        state = parent.state.upper()
        return state

    def resolve_context(parent, info):
        return parent.context

    def resolve_creator(parent, info):
        return parent.creator


class Status(ObjectType):
    contexts = List(StatusContext)

    def resolve_contexts(parent, info):
        return parent


class CheckRun(ObjectType):
    name = String()
    conclusion = String()

    def resolve_name(parent, info):
        return parent.name

    def resolve_conclusion(parent, info):
        if parent.conclusion:
            return parent.conclusion.upper()
        return None


class CheckRuns(ObjectType):
    nodes = List(CheckRun)

    def resolve_nodes(parent, info):
        return parent


class App(ObjectType):
    slug = String()
    name = String()


class CheckSuite(ObjectType):
    app = Field(App)
    checkRuns = Field(CheckRuns, first=Int())

    def resolve_app(parent, info):
        if not parent:
            return None
        return parent[0].app

    def resolve_checkRuns(parent, info, first=None):
        # We only want to return the latest result for a check run per app.
        # Since the check runs are ordered from latest to oldest result we
        # need to traverse the list in reverse order.
        check_runs_by_name = {
            "{}:{}".format(cr.app, cr.name): cr for cr in reversed(parent)
        }
        return check_runs_by_name.values()


class CheckSuites(ObjectType):

    nodes = List(CheckSuite)

    def resolve_nodes(parent, info):
        # Note: we only use a single check suite in the tests so return a
        # single item to keep it simple.
        return [parent]


class Commit(ObjectType):

    class Meta:
        # Graphql object type that defaults to the class name, but we require
        # 'Commit'.
        name = 'Commit'

    status = Field(Status)
    checkSuites = Field(CheckSuites, first=Int())

    def resolve_status(parent, info):
        seen = set()
        result = []
        for status in parent._statuses:
            if status.context not in seen:
                seen.add(status.context)
                result.append(status)
        # Github returns None if there are no results
        return result or None

    def resolve_checkSuites(parent, info, first=None):
        # Tests only utilize one check suite so return all runs for that.
        return parent._check_runs


class PullRequest(ObjectType):
    isDraft = Boolean()
    reviewDecision = String()
    mergeable = String()

    def resolve_isDraft(parent, info):
        return parent.draft

    def resolve_mergeable(parent, info):
        return "MERGEABLE" if parent.mergeable else "CONFLICTING"

    def resolve_reviewDecision(parent, info):
        if hasattr(info.context, 'version') and info.context.version:
            if info.context.version < (2, 21, 0):
                raise Exception('Field unsupported')

        # Check branch protection rules if reviews are required
        org, project = parent.project.split('/')
        repo = info.context._data.repos[(org, project)]
        rule = repo._branch_protection_rules.get(parent.branch)
        if not rule or not rule.require_reviews:
            # Github returns None if there is no review required
            return None

        approvals = [r for r in parent.reviews
                     if r.data['state'] == 'APPROVED']
        if approvals:
            return 'APPROVED'

        return 'REVIEW_REQUIRED'


class Repository(ObjectType):
    name = String()
    branchProtectionRules = Field(BranchProtectionRules,
                                  first=Int(), after=String())
    pullRequest = Field(PullRequest, number=Int(required=True))
    object = Field(Commit, expression=String(required=True))

    def resolve_name(parent, info):
        org, name = parent.name.split('/')
        return name

    def resolve_branchProtectionRules(parent, info, first, after=None):
        if after is None:
            after = '0'
        after = int(after)
        values = list(parent._branch_protection_rules.values())
        return dict(
            length=len(values),
            nodes=values[after:after + first],
            first=first,
            after=after,
        )

    def resolve_pullRequest(parent, info, number):
        return parent.data.pull_requests.get(number)

    def resolve_object(parent, info, expression):
        return parent._commits.get(expression)


class FakeGithubQuery(ObjectType):
    repository = Field(Repository, owner=String(required=True),
                       name=String(required=True))
    node = Field(BranchProtectionRule, id=ID(required=True))

    def resolve_repository(root, info, owner, name):
        return info.context._data.repos.get((owner, name))

    def resolve_node(root, info, id):
        for repo in info.context._data.repos.values():
            for rule in repo._branch_protection_rules.values():
                if rule.id == id:
                    return rule


def getGrapheneSchema():
    return Schema(query=FakeGithubQuery, types=[ID])
