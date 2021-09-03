# Copyright 2018 SUSE Linux GmbH
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

import os

from zuul.lib import strings


def construct_build_params(uuid, sched, job, item, pipeline,
                           dependent_changes=[], merger_items=[],
                           redact_secrets_and_keys=True):
    """Returns a list of all the parameters needed to build a job.

    These parameters may be passed to zuul-executors (via ZK) to perform
    the job itself.

    Alternatively they contain enough information to load into another build
    environment - for example, a local runner.
    """
    tenant = pipeline.tenant
    project = dict(
        name=item.change.project.name,
        short_name=item.change.project.name.split('/')[-1],
        canonical_hostname=item.change.project.canonical_hostname,
        canonical_name=item.change.project.canonical_name,
        src_dir=os.path.join('src',
                             strings.workspace_project_path(
                                 item.change.project.canonical_hostname,
                                 item.change.project.name,
                                 job.workspace_scheme)),
    )

    zuul_params = dict(
        build=uuid,
        buildset=item.current_build_set.uuid,
        ref=item.change.ref,
        pipeline=pipeline.name,
        post_review=pipeline.post_review,
        job=job.name,
        voting=job.voting,
        project=project,
        tenant=tenant.name,
        timeout=job.timeout,
        event_id=item.event.zuul_event_id if item.event else None,
        jobtags=sorted(job.tags),
        _inheritance_path=list(job.inheritance_path))
    if job.artifact_data:
        zuul_params['artifacts'] = job.artifact_data
    if job.override_checkout:
        zuul_params['override_checkout'] = job.override_checkout
    if hasattr(item.change, 'branch'):
        zuul_params['branch'] = item.change.branch
    if hasattr(item.change, 'tag'):
        zuul_params['tag'] = item.change.tag
    if hasattr(item.change, 'number'):
        zuul_params['change'] = str(item.change.number)
    if hasattr(item.change, 'url'):
        zuul_params['change_url'] = item.change.url
    if hasattr(item.change, 'patchset'):
        zuul_params['patchset'] = str(item.change.patchset)
    if hasattr(item.change, 'message'):
        zuul_params['message'] = strings.b64encode(item.change.message)
    if (hasattr(item.change, 'oldrev') and item.change.oldrev
        and item.change.oldrev != '0' * 40):
        zuul_params['oldrev'] = item.change.oldrev
    if (hasattr(item.change, 'newrev') and item.change.newrev
        and item.change.newrev != '0' * 40):
        zuul_params['newrev'] = item.change.newrev
    zuul_params['projects'] = {}  # Set below
    zuul_params['items'] = dependent_changes
    zuul_params['child_jobs'] = list(item.job_graph.getDirectDependentJobs(
        job.name))

    params = dict()
    params['job'] = job.name
    params['timeout'] = job.timeout
    params['post_timeout'] = job.post_timeout
    params['items'] = merger_items
    params['projects'] = []
    if hasattr(item.change, 'branch'):
        params['branch'] = item.change.branch
    else:
        params['branch'] = None
    params['override_branch'] = job.override_branch
    params['override_checkout'] = job.override_checkout
    params['repo_state'] = item.current_build_set.repo_state
    params['ansible_version'] = job.ansible_version
    params['workspace_scheme'] = job.workspace_scheme

    def make_playbook(playbook):
        d = playbook.toDict(redact_secrets=redact_secrets_and_keys)
        for role in d['roles']:
            if role['type'] != 'zuul':
                continue
            project_metadata = item.job_graph.getProjectMetadata(
                role['project_canonical_name'])
            if project_metadata:
                role['project_default_branch'] = \
                    project_metadata.default_branch
            else:
                role['project_default_branch'] = 'master'
            role_trusted, role_project = item.pipeline.tenant.getProject(
                role['project_canonical_name'])
            role_connection = role_project.source.connection
            role['connection'] = role_connection.connection_name
            role['project'] = role_project.name
        return d

    if job.name != 'noop':
        params['playbooks'] = [make_playbook(x) for x in job.run]
        params['pre_playbooks'] = [make_playbook(x) for x in job.pre_run]
        params['post_playbooks'] = [make_playbook(x) for x in job.post_run]
        params['cleanup_playbooks'] = [make_playbook(x)
                                       for x in job.cleanup_run]

    params["nodeset"] = job.nodeset.toDict()
    params['ssh_keys'] = []
    if pipeline.post_review:
        if redact_secrets_and_keys:
            params['ssh_keys'].append("REDACTED")
        else:
            params['ssh_keys'].append(dict(
                connection_name=item.change.project.connection_name,
                project_name=item.change.project.name))
    params['vars'] = job.combined_variables
    params['extra_vars'] = job.extra_variables
    params['host_vars'] = job.host_variables
    params['group_vars'] = job.group_variables
    params['secret_vars'] = job.secret_parent_data
    params['zuul'] = zuul_params
    projects = set()
    required_projects = set()

    def make_project_dict(project, override_branch=None,
                          override_checkout=None):
        project_metadata = item.job_graph.getProjectMetadata(
            project.canonical_name)
        if project_metadata:
            project_default_branch = project_metadata.default_branch
        else:
            project_default_branch = 'master'
        connection = project.source.connection
        return dict(connection=connection.connection_name,
                    name=project.name,
                    canonical_name=project.canonical_name,
                    override_branch=override_branch,
                    override_checkout=override_checkout,
                    default_branch=project_default_branch)

    if job.required_projects:
        for job_project in job.required_projects.values():
            (trusted, project) = tenant.getProject(
                job_project.project_name)
            if project is None:
                raise Exception("Unknown project %s" %
                                (job_project.project_name,))
            params['projects'].append(
                make_project_dict(project,
                                  job_project.override_branch,
                                  job_project.override_checkout))
            projects.add(project)
            required_projects.add(project)
    for change in dependent_changes:
        try:
            (_, project) = item.pipeline.tenant.getProject(
                change['project']['canonical_name'])
            if not project:
                raise KeyError()
        except Exception:
            # We have to find the project this way because it may not
            # be registered in the tenant (ie, a foreign project).
            source = sched.connections.getSourceByCanonicalHostname(
                change['project']['canonical_hostname'])
            project = source.getProject(change['project']['name'])

        if project not in projects:
            params['projects'].append(make_project_dict(project))
            projects.add(project)
    for p in projects:
        zuul_params['projects'][p.canonical_name] = (dict(
            name=p.name,
            short_name=p.name.split('/')[-1],
            # Duplicate this into the dict too, so that iterating
            # project.values() is easier for callers
            canonical_name=p.canonical_name,
            canonical_hostname=p.canonical_hostname,
            src_dir=os.path.join('src',
                                 strings.workspace_project_path(
                                     p.canonical_hostname,
                                     p.name,
                                     job.workspace_scheme)),
            required=(p in required_projects),
        ))

    if item.event:
        params['zuul_event_id'] = item.event.zuul_event_id
    return params
