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

from graphene import Boolean, Field, Int, List, ObjectType, String


class FakePageInfo(ObjectType):
    end_cursor = String()
    has_next_page = Boolean()

    def resolve_end_cursor(parent, info):
        return 'testcursor'

    def resolve_has_next_page(parent, info):
        return False


class FakeRepository(ObjectType):
    name = String()

    def resolve_name(parent, info):
        # parent is (team, repo)
        org, name = parent[1].name.split('/')
        return name


class FakeRepositoryEdge(ObjectType):
    permission = String()
    node = Field(FakeRepository)

    def resolve_permission(parent, info):
        permission_map = {
            'pull': 'READ',
            'push': 'WRITE',
            'admin': 'ADMIN',
        }
        return permission_map[parent[0].permission]

    def resolve_node(parent, info):
        return parent


class FakeTeamRepositories(ObjectType):
    total_count = Int()
    page_info = Field(FakePageInfo)
    edges = List(FakeRepositoryEdge)

    def resolve_total_count(parent, info):
        return len(parent)

    def resolve_page_info(parent, info):
        return parent

    def resolve_edges(parent, info):
        return parent


class FakeTeam(ObjectType):
    slug = String()
    repositories = Field(FakeTeamRepositories, query=String(), first=Int())

    def resolve_slug(parent, info):
        return parent.slug

    def resolve_repositories(parent, info, query, first):
        slug = parent.slug
        repos = [(team, repo)
                 for repo in info.context.repos.values()
                 for team in repo._teams
                 if team.slug == slug
                 if query in repo.name]
        return repos


class FakeTeamEdge(ObjectType):
    node = Field(FakeTeam)

    def resolve_node(parent, info):
        return parent


class FakeTeams(ObjectType):
    total_count = Int()
    page_info = Field(FakePageInfo)
    edges = List(FakeTeamEdge)

    def resolve_total_count(parent, info):
        return len(parent)

    def resolve_page_info(parent, info):
        return parent

    def resolve_edges(parent, info):
        return parent


class FakeGithubOrg(ObjectType):
    teams = Field(FakeTeams, query=String(), first=Int())

    def resolve_teams(parent, info, query, first):
        teams = [team for team in parent.fake_teams if query in team.slug]
        return teams


class FakeGithubQuery(ObjectType):
    organization = Field(FakeGithubOrg, login=String(required=True))

    def resolve_organization(root, info, login):
        return info.context.organizations.get(login)
