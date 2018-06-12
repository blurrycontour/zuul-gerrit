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

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker, relationship
import graphene
from graphene import relay
from graphene_sqlalchemy import SQLAlchemyObjectType, SQLAlchemyConnectionField


class SqlSchema:
    log = logging.getLogger("zuul.web.graphql")

    def __init__(self, tenant, connection):
        self.connection = connection
        self.session = scoped_session(sessionmaker(
            autocommit=False, autoflush=False, bind=self.connection.engine))

        # Note: Model should be part of the sqlconnection module
        Base = declarative_base()
        Base.query = self.session.query_property()

        class BuildModel(Base):
            __tablename__ = connection.table_prefix + "zuul_build"
            id = Column(Integer, primary_key=True)
            buildset_id = Column(String, ForeignKey(
                connection.table_prefix + "zuul_buildset.id"))
            uuid = Column(String)
            job_name = Column(String)
            result = Column(String)
            voting = Column(Boolean)
            log_url = Column(String)

        class BuildSetModel(Base):
            __tablename__ = connection.table_prefix + "zuul_buildset"
            id = Column(Integer, primary_key=True)
            builds = relationship(BuildModel, lazy="subquery")
            pipeline = Column(String)
            project = Column(String)
            branch = Column(String)
            result = Column(String)
            tenant = Column(String)

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
                query = BuildModel.get_query(info)
                return query.outerjoin(
                    (BuildSetModel, BuildModel.buildset_id == BuildSetModel.id)
                ).filter(
                    BuildSetModel.tenant == tenant
                )

            def resolve_all_buildsets(self, info, **args):
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
