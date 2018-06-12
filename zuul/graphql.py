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

import logging
import graphene
from graphene import relay


class Pipeline(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node, )

    name = graphene.String(description='The name of the pipeline.')


class PipelineConnection(relay.Connection):
    class Meta:
        node = Pipeline


class Project(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node, )

    name = graphene.String(description='The name of the project')
    type = graphene.String(description='The type of the project')


class ProjectConnection(relay.Connection):
    class Meta:
        node = Project


class Job(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node, )

    name = graphene.String(description='The name of the job')
    description = graphene.String(description='The description of the job')


class JobConnection(relay.Connection):
    class Meta:
        node = Job


class Tenant(graphene.ObjectType):
    class Meta:
        interfaces = (relay.Node, )

    name = graphene.String(description='The name of the tenant.')
    pipelines = relay.ConnectionField(
        PipelineConnection, description='The pipelines used by the tenant.')
    projects = relay.ConnectionField(
        ProjectConnection, description='The projects of the tenant')
    jobs = relay.ConnectionField(
        JobConnection, description='The jobs of the tenant')

    def resolve_pipelines(self, info, **args):
        # Transform the instance ship_ids into real instances
        tenant = info.context.get('tenant')
        return [Pipeline(name=pipeline)
                for pipeline in tenant.layout.pipelines.keys()]

    def resolve_projects(self, info, **args):
        tenant = info.context.get('tenant')
        projects = []
        for project in tenant.config_projects:
            projects.append(Project(name=project.name, type="config"))
        for project in tenant.untrusted_projects:
            projects.append(Project(name=project.name, type="untrusted"))
        return projects

    def resolve_jobs(self, info, **args):
        tenant = info.context.get('tenant')
        jobs = []
        for job_name in sorted(tenant.layout.jobs):
            desc = None
            for tenant_job in tenant.layout.jobs[job_name]:
                if tenant_job.description:
                    desc = tenant_job.description.split('\n')[0]
                    break
            jobs.append(Job(name=job_name, description=desc))
        return jobs


class Query(graphene.ObjectType):
    tenant = graphene.Field(Tenant)
    node = relay.Node.Field()

    def resolve_tenant(self, info):
        return Tenant(name=info.context.get('tenant').name)


class Schema:
    log = logging.getLogger("zuul.graphql")

    def __init__(self):
        self.schema = graphene.Schema(query=Query, types=[Pipeline])

    def execute(self, tenant, query):
        result = self.schema.execute(
            query, context_value={'tenant': tenant})
        if result.invalid:
            self.log.error("Query %s failed: %s" % (query, str(result.errors)))
        return result.data
