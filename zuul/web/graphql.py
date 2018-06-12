# Copyright (c) 2018 Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Example Query:
{
  allBuildsets {
    edges {
      node {
        pipeline
        builds {
          edges {
            node {
              jobName
            }
          }
        }
      }
    }
  }
}
=>
{"allBuildsets": {
  "edges": [{"node": {"pipeline": "post", "builds": {"edges": [
                {"node": {"jobName": "config-update"}}]}}},
            {"node": {"pipeline": "check", "builds": {"edges": [
                {"node": {"jobName": "linters"}}]}}}]
}}
"""

import logging

from sqlalchemy.orm import scoped_session, sessionmaker
import graphene
from graphene import relay
from graphene_sqlalchemy import SQLAlchemyObjectType, SQLAlchemyConnectionField


class SqlSchema:
    log = logging.getLogger("zuul.web.graphql")

    def __init__(self, tenant, connection):
        self.connection = connection
        self.session = scoped_session(sessionmaker(
            autocommit=False, autoflush=False, bind=self.connection.engine))

        BuildModel = connection.buildModel
        BuildSetModel = connection.buildSetModel

        class Build(SQLAlchemyObjectType):
            class Meta:
                model = BuildModel
                interfaces = (relay.Node, )

        class BuildSet(SQLAlchemyObjectType):
            class Meta:
                model = BuildSetModel
                interfaces = (relay.Node, )

        class Query(graphene.ObjectType):
            node = relay.Node.Field()
            all_builds = SQLAlchemyConnectionField(Build)
            all_buildsets = SQLAlchemyConnectionField(BuildSet)

            def resolve_all_builds(self, info, **args):
                # Filter builds query by tenant
                query = BuildModel.get_query(info)
                return query.outerjoin(
                    (BuildSetModel, BuildModel.buildset_id == BuildSetModel.id)
                ).filter(
                    BuildSetModel.tenant == tenant
                )

            def resolve_all_buildsets(self, info, **args):
                # Filter buildsets query by tenant
                query = BuildSet.get_query(info)
                return query.filter(BuildSetModel.tenant == tenant)

        self.schema = graphene.Schema(query=Query, types=[Build, BuildSet])

    def execute(self, query):
        result = self.schema.execute(
            query, context_value={'session': self.session})
        if result.invalid:
            self.log.error("Query %s failed: %s" % (query, str(result.errors)))
        return result.data


schemas = {}


def execute(query, tenant, connection):
    engine = schemas.setdefault(
        connection.connection_name, SqlSchema(tenant, connection))
    return engine.execute(query)
