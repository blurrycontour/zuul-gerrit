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

import base64
from contextlib import contextmanager
import copy
import os
import logging
import six
import pprint
import textwrap

import voluptuous as vs

from zuul import model
from zuul.lib import yamlutil as yaml
import zuul.manager.dependent
import zuul.manager.independent
from zuul import change_matcher
from zuul.lib import encryption


# Several forms accept either a single item or a list, this makes
# specifying that in the schema easy (and explicit).
def to_list(x):
    return vs.Any([x], x)


def as_list(item):
    if not item:
        return []
    if isinstance(item, list):
        return item
    return [item]


class ConfigurationSyntaxError(Exception):
    pass


class NodeFromGroupNotFoundError(Exception):
    def __init__(self, nodeset, node, group):
        message = textwrap.dedent("""\
        In nodeset "{nodeset}" the group "{group}" contains a
        node named "{node}" which is not defined in the nodeset.""")
        message = textwrap.fill(message.format(nodeset=nodeset,
                                               node=node, group=group))
        super(NodeFromGroupNotFoundError, self).__init__(message)


class DuplicateNodeError(Exception):
    def __init__(self, nodeset, node):
        message = textwrap.dedent("""\
        In nodeset "{nodeset}" the node "{node}" appears multiple times.
        Node names must be unique within a nodeset.""")
        message = textwrap.fill(message.format(nodeset=nodeset,
                                               node=node))
        super(DuplicateNodeError, self).__init__(message)


class DuplicateGroupError(Exception):
    def __init__(self, nodeset, group):
        message = textwrap.dedent("""\
        In nodeset "{nodeset}" the group "{group}" appears multiple times.
        Group names must be unique within a nodeset.""")
        message = textwrap.fill(message.format(nodeset=nodeset,
                                               group=group))
        super(DuplicateGroupError, self).__init__(message)


class ProjectNotFoundError(Exception):
    def __init__(self, project):
        message = textwrap.dedent("""\
        The project "{project}" was not found.  All projects
        referenced within a Zuul configuration must first be
        added to the main configuration file by the Zuul
        administrator.""")
        message = textwrap.fill(message.format(project=project))
        super(ProjectNotFoundError, self).__init__(message)


class PipelineNotPermittedError(Exception):
    def __init__(self):
        message = textwrap.dedent("""\
        Pipelines may not be defined in untrusted repos,
        they may only be defined in config repos.""")
        message = textwrap.fill(message)
        super(PipelineNotPermittedError, self).__init__(message)


class ProjectNotPermittedError(Exception):
    def __init__(self):
        message = textwrap.dedent("""\
        Within an untrusted project, the only project definition
        permitted is that of the project itself.""")
        message = textwrap.fill(message)
        super(ProjectNotPermittedError, self).__init__(message)


def indent(s):
    return '\n'.join(['  ' + x for x in s.split('\n')])


@contextmanager
def configuration_exceptions(stanza, conf):
    try:
        yield
    except ConfigurationSyntaxError:
        raise
    except Exception as e:
        conf = copy.deepcopy(conf)
        context = conf.pop('_source_context')
        start_mark = conf.pop('_start_mark')
        intro = textwrap.fill(textwrap.dedent("""\
        Zuul encountered a syntax error while parsing its configuration in the
        repo {repo} on branch {branch}.  The error was:""".format(
            repo=context.project.name,
            branch=context.branch,
        )))

        m = textwrap.dedent("""\
        {intro}

        {error}

        The error appears in a {stanza} stanza with the content:

        {content}

        {start_mark}""")

        m = m.format(intro=intro,
                     error=indent(str(e)),
                     stanza=stanza,
                     content=indent(pprint.pformat(conf)),
                     start_mark=str(start_mark))
        raise ConfigurationSyntaxError(m)


class ZuulSafeLoader(yaml.SafeLoader):
    zuul_node_types = frozenset(('job', 'nodeset', 'secret', 'pipeline',
                                 'project', 'project-template',
                                 'semaphore'))

    def __init__(self, stream, context):
        super(ZuulSafeLoader, self).__init__(stream)
        self.name = str(context)
        self.zuul_context = context

    def construct_mapping(self, node, deep=False):
        r = super(ZuulSafeLoader, self).construct_mapping(node, deep)
        keys = frozenset(r.keys())
        if len(keys) == 1 and keys.intersection(self.zuul_node_types):
            d = list(r.values())[0]
            if isinstance(d, dict):
                d['_start_mark'] = node.start_mark
                d['_source_context'] = self.zuul_context
        return r


def safe_load_yaml(stream, context):
    loader = ZuulSafeLoader(stream, context)
    try:
        return loader.get_single_data()
    except yaml.YAMLError as e:
        m = """
Zuul encountered a syntax error while parsing its configuration in the
repo {repo} on branch {branch}.  The error was:

  {error}
"""
        m = m.format(repo=context.project.name,
                     branch=context.branch,
                     error=str(e))
        raise ConfigurationSyntaxError(m)
    finally:
        loader.dispose()


class EncryptedPKCS1_OAEP(yaml.YAMLObject):
    yaml_tag = u'!encrypted/pkcs1-oaep'
    yaml_loader = yaml.SafeLoader

    def __init__(self, ciphertext):
        self.ciphertext = base64.b64decode(ciphertext)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, EncryptedPKCS1_OAEP):
            return False
        return (self.ciphertext == other.ciphertext)

    @classmethod
    def from_yaml(cls, loader, node):
        return cls(node.value)

    def decrypt(self, private_key):
        return encryption.decrypt_pkcs1_oaep(self.ciphertext,
                                             private_key).decode('utf8')


class NodeSetParser(object):
    @staticmethod
    def getSchema():
        node = {vs.Required('name'): str,
                vs.Required('label'): str,
                }

        group = {vs.Required('name'): str,
                 vs.Required('nodes'): to_list(str),
                 }

        nodeset = {vs.Required('name'): str,
                   vs.Required('nodes'): to_list(node),
                   'groups': to_list(group),
                   '_source_context': model.SourceContext,
                   '_start_mark': yaml.Mark,
                   }

        return vs.Schema(nodeset)

    @staticmethod
    def fromYaml(layout, conf):
        NodeSetParser.getSchema()(conf)
        ns = model.NodeSet(conf['name'])
        node_names = set()
        group_names = set()
        for conf_node in as_list(conf['nodes']):
            if conf_node['name'] in node_names:
                raise DuplicateNodeError(conf['name'], conf_node['name'])
            node = model.Node(conf_node['name'], conf_node['label'])
            ns.addNode(node)
            node_names.add(conf_node['name'])
        for conf_group in as_list(conf.get('groups', [])):
            for node_name in as_list(conf_group['nodes']):
                if node_name not in node_names:
                    raise NodeFromGroupNotFoundError(conf['name'], node_name,
                                                     conf_group['name'])
            if conf_group['name'] in group_names:
                raise DuplicateGroupError(conf['name'], conf_group['name'])
            group = model.Group(conf_group['name'], conf_group['nodes'])
            ns.addGroup(group)
            group_names.add(conf_group['name'])
        return ns


class SecretParser(object):
    @staticmethod
    def getSchema():
        data = {str: vs.Any(str, EncryptedPKCS1_OAEP)}

        secret = {vs.Required('name'): str,
                  vs.Required('data'): data,
                  '_source_context': model.SourceContext,
                  '_start_mark': yaml.Mark,
                  }

        return vs.Schema(secret)

    @staticmethod
    def fromYaml(layout, conf):
        with configuration_exceptions('secret', conf):
            SecretParser.getSchema()(conf)
        s = model.Secret(conf['name'], conf['_source_context'])
        s.secret_data = conf['data']
        return s


class JobParser(object):
    @staticmethod
    def getSchema():
        auth = {'secrets': to_list(str),
                'inherit': bool,
                }

        node = {vs.Required('name'): str,
                vs.Required('label'): str,
                }

        zuul_role = {vs.Required('zuul'): str,
                     'name': str}

        galaxy_role = {vs.Required('galaxy'): str,
                       'name': str}

        role = vs.Any(zuul_role, galaxy_role)

        job_project = {vs.Required('name'): str,
                       'override-branch': str}

        job = {vs.Required('name'): str,
               'parent': str,
               'failure-message': str,
               'success-message': str,
               'failure-url': str,
               'success-url': str,
               'hold-following-changes': bool,
               'voting': bool,
               'semaphore': str,
               'tags': to_list(str),
               'branches': to_list(str),
               'files': to_list(str),
               'auth': auth,
               'irrelevant-files': to_list(str),
               'nodes': vs.Any([node], str),
               'timeout': int,
               'attempts': int,
               'pre-run': to_list(str),
               'post-run': to_list(str),
               'run': str,
               '_source_context': model.SourceContext,
               '_start_mark': yaml.Mark,
               'roles': to_list(role),
               'required-projects': to_list(vs.Any(job_project, str)),
               'vars': dict,
               'dependencies': to_list(str),
               'allowed-projects': to_list(str),
               'override-branch': str,
               'description': str,
               }

        return vs.Schema(job)

    simple_attributes = [
        'timeout',
        'workspace',
        'voting',
        'hold-following-changes',
        'semaphore',
        'attempts',
        'failure-message',
        'success-message',
        'failure-url',
        'success-url',
        'override-branch',
    ]

    @staticmethod
    def _getImpliedBranches(reference, job, project_pipeline):
        # If the current job definition is not in the same branch as
        # the reference definition of this job, and this is a project
        # repo, add an implicit branch matcher for this branch
        # (assuming there are no explicit branch matchers).  But only
        # for top-level job definitions and variants.
        # Project-pipeline job variants should more closely attach to
        # their branch if they appear in a project-repo.
        if (reference and
            reference.source_context and
            reference.source_context.branch != job.source_context.branch):
            same_context = False
        else:
            same_context = True

        if (job.source_context and
            (not job.source_context.trusted) and
            ((not same_context) or project_pipeline)):
            return [job.source_context.branch]
        return None

    @staticmethod
    def fromYaml(tenant, layout, conf, project_pipeline=False):
        with configuration_exceptions('job', conf):
            JobParser.getSchema()(conf)

        # NB: The default detection system in the Job class requires
        # that we always assign values directly rather than modifying
        # them (e.g., "job.run = ..." rather than
        # "job.run.append(...)").

        reference = layout.jobs.get(conf['name'], [None])[0]

        job = model.Job(conf['name'])
        job.source_context = conf.get('_source_context')
        if 'auth' in conf:
            job.auth = model.AuthContext()
            if 'inherit' in conf['auth']:
                job.auth.inherit = conf['auth']['inherit']

            for secret_name in conf['auth'].get('secrets', []):
                secret = layout.secrets[secret_name]
                if secret.source_context != job.source_context:
                    raise Exception(
                        "Unable to use secret %s.  Secrets must be "
                        "defined in the same project in which they "
                        "are used" % secret_name)
                job.auth.secrets.append(secret.decrypt(
                    job.source_context.project.private_key))

        if 'parent' in conf:
            parent = layout.getJob(conf['parent'])
            job.inheritFrom(parent)

        for pre_run_name in as_list(conf.get('pre-run')):
            full_pre_run_name = os.path.join('playbooks', pre_run_name)
            pre_run = model.PlaybookContext(job.source_context,
                                            full_pre_run_name)
            job.pre_run = job.pre_run + (pre_run,)
        for post_run_name in as_list(conf.get('post-run')):
            full_post_run_name = os.path.join('playbooks', post_run_name)
            post_run = model.PlaybookContext(job.source_context,
                                             full_post_run_name)
            job.post_run = (post_run,) + job.post_run
        if 'run' in conf:
            run_name = os.path.join('playbooks', conf['run'])
            run = model.PlaybookContext(job.source_context, run_name)
            job.run = (run,)
        else:
            if not project_pipeline:
                run_name = os.path.join('playbooks', job.name)
                run = model.PlaybookContext(job.source_context, run_name)
                job.implied_run = (run,) + job.implied_run

        for k in JobParser.simple_attributes:
            a = k.replace('-', '_')
            if k in conf:
                setattr(job, a, conf[k])
        if 'nodes' in conf:
            conf_nodes = conf['nodes']
            if isinstance(conf_nodes, six.string_types):
                # This references an existing named nodeset in the layout.
                ns = layout.nodesets[conf_nodes]
            else:
                ns = model.NodeSet()
                for conf_node in conf_nodes:
                    node = model.Node(conf_node['name'], conf_node['label'])
                    ns.addNode(node)
            job.nodeset = ns

        if 'required-projects' in conf:
            new_projects = {}
            projects = as_list(conf.get('required-projects', []))
            for project in projects:
                if isinstance(project, dict):
                    project_name = project['name']
                    project_override_branch = project.get('override-branch')
                else:
                    project_name = project
                    project_override_branch = None
                (trusted, project) = tenant.getProject(project_name)
                if project is None:
                    raise Exception("Unknown project %s" % (project_name,))
                job_project = model.JobProject(project_name,
                                               project_override_branch)
                new_projects[project_name] = job_project
            job.updateProjects(new_projects)

        tags = conf.get('tags')
        if tags:
            # Tags are merged via a union rather than a
            # destructive copy because they are intended to
            # accumulate onto any previously applied tags.
            job.tags = job.tags.union(set(tags))

        job.dependencies = frozenset(as_list(conf.get('dependencies')))

        if 'roles' in conf:
            roles = []
            for role in conf.get('roles', []):
                if 'zuul' in role:
                    r = JobParser._makeZuulRole(tenant, job, role)
                    if r:
                        roles.append(r)
            job.roles = job.roles.union(set(roles))

        variables = conf.get('vars', None)
        if variables:
            job.updateVariables(variables)

        allowed_projects = conf.get('allowed-projects', None)
        if allowed_projects:
            allowed = []
            for p in as_list(allowed_projects):
                (trusted, project) = tenant.getProject(p)
                if project is None:
                    raise Exception("Unknown project %s" % (p,))
                allowed.append(project.name)
            job.allowed_projects = frozenset(allowed)

        # If the current job definition is not in the same branch as
        # the reference definition of this job, and this is a project
        # repo, add an implicit branch matcher for this branch
        # (assuming there are no explicit branch matchers).  But only
        # for top-level job definitions and variants.
        # Project-pipeline job variants should more closely attach to
        # their branch if they appear in a project-repo.

        branches = None
        if (project_pipeline or 'branches' not in conf):
            branches = JobParser._getImpliedBranches(
                reference, job, project_pipeline)
        if (not branches) and ('branches' in conf):
            branches = as_list(conf['branches'])
        if branches:
            matchers = []
            for branch in branches:
                matchers.append(change_matcher.BranchMatcher(branch))
            job.branch_matcher = change_matcher.MatchAny(matchers)
        if 'files' in conf:
            matchers = []
            for fn in as_list(conf['files']):
                matchers.append(change_matcher.FileMatcher(fn))
            job.file_matcher = change_matcher.MatchAny(matchers)
        if 'irrelevant-files' in conf:
            matchers = []
            for fn in as_list(conf['irrelevant-files']):
                matchers.append(change_matcher.FileMatcher(fn))
            job.irrelevant_file_matcher = change_matcher.MatchAllFiles(
                matchers)
        return job

    @staticmethod
    def _makeZuulRole(tenant, job, role):
        name = role['zuul'].split('/')[-1]

        (trusted, project) = tenant.getProject(role['zuul'])
        if project is None:
            return None

        return model.ZuulRole(role.get('name', name),
                              project.connection_name,
                              project.name)


class ProjectTemplateParser(object):
    log = logging.getLogger("zuul.ProjectTemplateParser")

    @staticmethod
    def getSchema(layout):
        project_template = {
            vs.Required('name'): str,
            'merge-mode': vs.Any(
                'merge', 'merge-resolve',
                'cherry-pick'),
            '_source_context': model.SourceContext,
            '_start_mark': yaml.Mark,
        }

        for p in layout.pipelines.values():
            project_template[p.name] = {'queue': str,
                                        'jobs': [vs.Any(str, dict)]}
        return vs.Schema(project_template)

    @staticmethod
    def fromYaml(tenant, layout, conf):
        with configuration_exceptions('project or project-template', conf):
            ProjectTemplateParser.getSchema(layout)(conf)
        # Make a copy since we modify this later via pop
        conf = copy.deepcopy(conf)
        project_template = model.ProjectConfig(conf['name'])
        source_context = conf['_source_context']
        start_mark = conf['_start_mark']
        for pipeline in layout.pipelines.values():
            conf_pipeline = conf.get(pipeline.name)
            if not conf_pipeline:
                continue
            project_pipeline = model.ProjectPipelineConfig()
            project_template.pipelines[pipeline.name] = project_pipeline
            project_pipeline.queue_name = conf_pipeline.get('queue')
            ProjectTemplateParser._parseJobList(
                tenant, layout, conf_pipeline.get('jobs', []),
                source_context, start_mark, project_pipeline.job_list)
        return project_template

    @staticmethod
    def _parseJobList(tenant, layout, conf, source_context,
                      start_mark, job_list):
        for conf_job in conf:
            if isinstance(conf_job, six.string_types):
                attrs = dict(name=conf_job)
            elif isinstance(conf_job, dict):
                # A dictionary in a job tree may override params
                jobname, attrs = list(conf_job.items())[0]
                if attrs:
                    # We are overriding params, so make a new job def
                    attrs['name'] = jobname
                else:
                    # Not overriding, so add a blank job
                    attrs = dict(name=jobname)
            else:
                raise Exception("Job must be a string or dictionary")
            attrs['_source_context'] = source_context
            attrs['_start_mark'] = start_mark
            job_list.addJob(JobParser.fromYaml(tenant, layout, attrs,
                                               project_pipeline=True))


class ProjectParser(object):
    log = logging.getLogger("zuul.ProjectParser")

    @staticmethod
    def getSchema(layout):
        project = {
            vs.Required('name'): str,
            'templates': [str],
            'merge-mode': vs.Any('merge', 'merge-resolve',
                                 'cherry-pick'),
            'default-branch': str,
            '_source_context': model.SourceContext,
            '_start_mark': yaml.Mark,
        }

        for p in layout.pipelines.values():
            project[p.name] = {'queue': str,
                               'jobs': [vs.Any(str, dict)]}
        return vs.Schema(project)

    @staticmethod
    def fromYaml(tenant, layout, conf_list):
        for conf in conf_list:
            with configuration_exceptions('project', conf):
                ProjectParser.getSchema(layout)(conf)

        with configuration_exceptions('project', conf_list[0]):
            project_name = conf_list[0]['name']
            (trusted, project) = tenant.getProject(project_name)
            if project is None:
                raise ProjectNotFoundError(project_name)
            project_config = model.ProjectConfig(project.canonical_name)

        configs = []
        for conf in conf_list:
            with configuration_exceptions('project', conf):
                if not conf['_source_context'].trusted:
                    if project != conf['_source_context'].project:
                        raise ProjectNotPermittedError()

            # Make a copy since we modify this later via pop
            conf = copy.deepcopy(conf)
            conf_templates = conf.pop('templates', [])
            # The way we construct a project definition is by parsing the
            # definition as a template, then applying all of the
            # templates, including the newly parsed one, in order.
            project_template = ProjectTemplateParser.fromYaml(
                tenant, layout, conf)
            configs.extend([layout.project_templates[name]
                            for name in conf_templates])
            configs.append(project_template)
            # Set the following values to the first one that we find and
            # ignore subsequent settings.
            mode = conf.get('merge-mode')
            if mode and project_config.merge_mode is None:
                project_config.merge_mode = model.MERGER_MAP[mode]
            default_branch = conf.get('default-branch')
            if default_branch and project_config.default_branch is None:
                project_config.default_branch = default_branch
        if project_config.merge_mode is None:
            # If merge mode was not specified in any project stanza,
            # set it to the default.
            project_config.merge_mode = model.MERGER_MAP['merge-resolve']
        if project_config.default_branch is None:
            project_config.default_branch = 'master'
        for pipeline in layout.pipelines.values():
            project_pipeline = model.ProjectPipelineConfig()
            queue_name = None
            # For every template, iterate over the job tree and replace or
            # create the jobs in the final definition as needed.
            pipeline_defined = False
            for template in configs:
                if pipeline.name in template.pipelines:
                    ProjectParser.log.debug(
                        "Applying template %s to pipeline %s" %
                        (template.name, pipeline.name))
                    pipeline_defined = True
                    template_pipeline = template.pipelines[pipeline.name]
                    project_pipeline.job_list.inheritFrom(
                        template_pipeline.job_list)
                    if template_pipeline.queue_name:
                        queue_name = template_pipeline.queue_name
            if queue_name:
                project_pipeline.queue_name = queue_name
            if pipeline_defined:
                project_config.pipelines[pipeline.name] = project_pipeline
        return project_config


class PipelineParser(object):
    log = logging.getLogger("zuul.PipelineParser")

    # A set of reporter configuration keys to action mapping
    reporter_actions = {
        'start': 'start_actions',
        'success': 'success_actions',
        'failure': 'failure_actions',
        'merge-failure': 'merge_failure_actions',
        'disabled': 'disabled_actions',
    }

    @staticmethod
    def getDriverSchema(dtype, connections):
        methods = {
            'trigger': 'getTriggerSchema',
            'reporter': 'getReporterSchema',
            'require': 'getRequireSchema',
            'reject': 'getRejectSchema',
        }

        schema = {}
        # Add the configured connections as available layout options
        for connection_name, connection in connections.connections.items():
            method = getattr(connection.driver, methods[dtype], None)
            if method:
                schema[connection_name] = to_list(method())

        return schema

    @staticmethod
    def getSchema(layout, connections):
        manager = vs.Any('independent',
                         'dependent')

        precedence = vs.Any('normal', 'low', 'high')

        approval = vs.Schema({'username': str,
                              'email-filter': str,
                              'email': str,
                              'older-than': str,
                              'newer-than': str,
                              }, extra=vs.ALLOW_EXTRA)

        require = {'approval': to_list(approval),
                   'open': bool,
                   'current-patchset': bool,
                   'status': to_list(str)}

        reject = {'approval': to_list(approval)}

        window = vs.All(int, vs.Range(min=0))
        window_floor = vs.All(int, vs.Range(min=1))
        window_type = vs.Any('linear', 'exponential')
        window_factor = vs.All(int, vs.Range(min=1))

        pipeline = {vs.Required('name'): str,
                    vs.Required('manager'): manager,
                    'precedence': precedence,
                    'description': str,
                    'require': require,
                    'reject': reject,
                    'success-message': str,
                    'failure-message': str,
                    'merge-failure-message': str,
                    'footer-message': str,
                    'dequeue-on-new-patchset': bool,
                    'ignore-dependencies': bool,
                    'allow-secrets': bool,
                    'disable-after-consecutive-failures':
                        vs.All(int, vs.Range(min=1)),
                    'window': window,
                    'window-floor': window_floor,
                    'window-increase-type': window_type,
                    'window-increase-factor': window_factor,
                    'window-decrease-type': window_type,
                    'window-decrease-factor': window_factor,
                    '_source_context': model.SourceContext,
                    '_start_mark': yaml.Mark,
                    }
        pipeline['require'] = PipelineParser.getDriverSchema('require',
                                                             connections)
        pipeline['reject'] = PipelineParser.getDriverSchema('reject',
                                                            connections)
        pipeline['trigger'] = vs.Required(
            PipelineParser.getDriverSchema('trigger', connections))
        for action in ['start', 'success', 'failure', 'merge-failure',
                       'disabled']:
            pipeline[action] = PipelineParser.getDriverSchema('reporter',
                                                              connections)
        return vs.Schema(pipeline)

    @staticmethod
    def fromYaml(layout, connections, scheduler, conf):
        with configuration_exceptions('pipeline', conf):
            PipelineParser.getSchema(layout, connections)(conf)
        pipeline = model.Pipeline(conf['name'], layout)
        pipeline.description = conf.get('description')

        precedence = model.PRECEDENCE_MAP[conf.get('precedence')]
        pipeline.precedence = precedence
        pipeline.failure_message = conf.get('failure-message',
                                            "Build failed.")
        pipeline.merge_failure_message = conf.get(
            'merge-failure-message', "Merge Failed.\n\nThis change or one "
            "of its cross-repo dependencies was unable to be "
            "automatically merged with the current state of its "
            "repository. Please rebase the change and upload a new "
            "patchset.")
        pipeline.success_message = conf.get('success-message',
                                            "Build succeeded.")
        pipeline.footer_message = conf.get('footer-message', "")
        pipeline.start_message = conf.get('start-message',
                                          "Starting {pipeline.name} jobs.")
        pipeline.dequeue_on_new_patchset = conf.get(
            'dequeue-on-new-patchset', True)
        pipeline.ignore_dependencies = conf.get(
            'ignore-dependencies', False)
        pipeline.allow_secrets = conf.get('allow-secrets', False)

        for conf_key, action in PipelineParser.reporter_actions.items():
            reporter_set = []
            if conf.get(conf_key):
                for reporter_name, params \
                    in conf.get(conf_key).items():
                    reporter = connections.getReporter(reporter_name,
                                                       params)
                    reporter.setAction(conf_key)
                    reporter_set.append(reporter)
            setattr(pipeline, action, reporter_set)

        # If merge-failure actions aren't explicit, use the failure actions
        if not pipeline.merge_failure_actions:
            pipeline.merge_failure_actions = pipeline.failure_actions

        pipeline.disable_at = conf.get(
            'disable-after-consecutive-failures', None)

        pipeline.window = conf.get('window', 20)
        pipeline.window_floor = conf.get('window-floor', 3)
        pipeline.window_increase_type = conf.get(
            'window-increase-type', 'linear')
        pipeline.window_increase_factor = conf.get(
            'window-increase-factor', 1)
        pipeline.window_decrease_type = conf.get(
            'window-decrease-type', 'exponential')
        pipeline.window_decrease_factor = conf.get(
            'window-decrease-factor', 2)

        manager_name = conf['manager']
        if manager_name == 'dependent':
            manager = zuul.manager.dependent.DependentPipelineManager(
                scheduler, pipeline)
        elif manager_name == 'independent':
            manager = zuul.manager.independent.IndependentPipelineManager(
                scheduler, pipeline)

        pipeline.setManager(manager)
        layout.pipelines[conf['name']] = pipeline

        for source_name, require_config in conf.get('require', {}).items():
            source = connections.getSource(source_name)
            manager.ref_filters.extend(
                source.getRequireFilters(require_config))

        for source_name, reject_config in conf.get('reject', {}).items():
            source = connections.getSource(source_name)
            manager.ref_filters.extend(
                source.getRejectFilters(reject_config))

        for trigger_name, trigger_config in conf.get('trigger').items():
            trigger = connections.getTrigger(trigger_name, trigger_config)
            pipeline.triggers.append(trigger)
            manager.event_filters.extend(
                trigger.getEventFilters(conf['trigger'][trigger_name]))

        return pipeline


class SemaphoreParser(object):
    @staticmethod
    def getSchema():
        semaphore = {vs.Required('name'): str,
                     'max': int,
                     '_source_context': model.SourceContext,
                     '_start_mark': yaml.Mark,
                     }

        return vs.Schema(semaphore)

    @staticmethod
    def fromYaml(conf):
        SemaphoreParser.getSchema()(conf)
        semaphore = model.Semaphore(conf['name'], conf.get('max', 1))
        semaphore.source_context = conf.get('_source_context')
        return semaphore


class TenantParser(object):
    log = logging.getLogger("zuul.TenantParser")

    classes = vs.Any('pipeline', 'job', 'semaphore', 'project',
                     'project-template', 'nodeset', 'secret')

    project_dict = {str: {
        'include': to_list(classes),
        'exclude': to_list(classes),
    }}

    project = vs.Any(str, project_dict)

    group = {
        'include': to_list(classes),
        'exclude': to_list(classes),
        vs.Required('projects'): to_list(project),
    }

    project_or_group = vs.Any(project, group)

    tenant_source = vs.Schema({
        'config-projects': to_list(project_or_group),
        'untrusted-projects': to_list(project_or_group),
    })

    @staticmethod
    def validateTenantSources(connections):
        def v(value, path=[]):
            if isinstance(value, dict):
                for k, val in value.items():
                    connections.getSource(k)
                    TenantParser.validateTenantSource(val, path + [k])
            else:
                raise vs.Invalid("Invalid tenant source", path)
        return v

    @staticmethod
    def validateTenantSource(value, path=[]):
        TenantParser.tenant_source(value)

    @staticmethod
    def getSchema(connections=None):
        tenant = {vs.Required('name'): str,
                  'source': TenantParser.validateTenantSources(connections)}
        return vs.Schema(tenant)

    @staticmethod
    def fromYaml(base, project_key_dir, connections, scheduler, merger, conf,
                 cached):
        TenantParser.getSchema(connections)(conf)
        tenant = model.Tenant(conf['name'])
        tenant.unparsed_config = conf
        unparsed_config = model.UnparsedTenantConfig()
        config_projects, untrusted_projects = \
            TenantParser._loadTenantProjects(
                project_key_dir, connections, conf)
        for project in config_projects:
            tenant.addConfigProject(project)
        for project in untrusted_projects:
            tenant.addUntrustedProject(project)
        tenant.config_projects_config, tenant.untrusted_projects_config = \
            TenantParser._loadTenantInRepoLayouts(merger, connections,
                                                  tenant.config_projects,
                                                  tenant.untrusted_projects,
                                                  cached)
        unparsed_config.extend(tenant.config_projects_config)
        unparsed_config.extend(tenant.untrusted_projects_config)
        tenant.layout = TenantParser._parseLayout(base, tenant,
                                                  unparsed_config,
                                                  scheduler,
                                                  connections)
        return tenant

    @staticmethod
    def _loadProjectKeys(project_key_dir, connection_name, project):
        project.private_key_file = (
            os.path.join(project_key_dir, connection_name,
                         project.name + '.pem'))

        TenantParser._generateKeys(project)
        TenantParser._loadKeys(project)

    @staticmethod
    def _generateKeys(project):
        if os.path.isfile(project.private_key_file):
            return

        key_dir = os.path.dirname(project.private_key_file)
        if not os.path.isdir(key_dir):
            os.makedirs(key_dir, 0o700)

        TenantParser.log.info(
            "Generating RSA keypair for project %s" % (project.name,)
        )
        private_key, public_key = encryption.generate_rsa_keypair()
        pem_private_key = encryption.serialize_rsa_private_key(private_key)

        # Dump keys to filesystem.  We only save the private key
        # because the public key can be constructed from it.
        TenantParser.log.info(
            "Saving RSA keypair for project %s to %s" % (
                project.name, project.private_key_file)
        )
        with open(project.private_key_file, 'wb') as f:
            f.write(pem_private_key)

        # Ensure private key is read/write for zuul user only.
        os.chmod(project.private_key_file, 0o600)

    @staticmethod
    def _loadKeys(project):
        # Check the key files specified are there
        if not os.path.isfile(project.private_key_file):
            raise Exception(
                'Private key file {0} not found'.format(
                    project.private_key_file))

        # Load keypair
        with open(project.private_key_file, "rb") as f:
            (project.private_key, project.public_key) = \
                encryption.deserialize_rsa_keypair(f.read())

    @staticmethod
    def _getProject(source, conf, current_include):
        if isinstance(conf, six.string_types):
            # Return a project object whether conf is a dict or a str
            project = source.getProject(conf)
            project_include = current_include
        else:
            project_name = list(conf.keys())[0]
            project = source.getProject(project_name)

            project_include = frozenset(
                as_list(conf[project_name].get('include', [])))
            if not project_include:
                project_include = current_include
            project_exclude = frozenset(
                as_list(conf[project_name].get('exclude', [])))
            if project_exclude:
                project_include = frozenset(project_include - project_exclude)

        project.load_classes = frozenset(project_include)
        return project

    @staticmethod
    def _getProjects(source, conf, current_include):
        # Return a project object whether conf is a dict or a str
        projects = []
        if isinstance(conf, six.string_types):
            # A simple project name string
            projects.append(TenantParser._getProject(
                source, conf, current_include))
        elif len(conf.keys()) > 1 and 'projects' in conf:
            # This is a project group
            if 'include' in conf:
                current_include = set(as_list(conf['include']))
            else:
                current_include = current_include.copy()
            if 'exclude' in conf:
                exclude = set(as_list(conf['exclude']))
                current_include = current_include - exclude
            for project in conf['projects']:
                sub_projects = TenantParser._getProjects(source, project,
                                                         current_include)
                projects.extend(sub_projects)
        elif len(conf.keys()) == 1:
            # A project with overrides
            projects.append(TenantParser._getProject(
                source, conf, current_include))
        else:
            raise Exception("Unable to parse project %s", conf)
        return projects

    @staticmethod
    def _loadTenantProjects(project_key_dir, connections, conf_tenant):
        config_projects = []
        untrusted_projects = []

        default_include = frozenset(['pipeline', 'job', 'semaphore', 'project',
                                     'secret', 'project-template', 'nodeset'])

        for source_name, conf_source in conf_tenant.get('source', {}).items():
            source = connections.getSource(source_name)

            current_include = default_include
            for conf_repo in conf_source.get('config-projects', []):
                projects = TenantParser._getProjects(source, conf_repo,
                                                     current_include)
                for project in projects:
                    TenantParser._loadProjectKeys(
                        project_key_dir, source_name, project)
                    config_projects.append(project)

            current_include = frozenset(default_include - set(['pipeline']))
            for conf_repo in conf_source.get('untrusted-projects', []):
                projects = TenantParser._getProjects(source, conf_repo,
                                                     current_include)
                for project in projects:
                    TenantParser._loadProjectKeys(
                        project_key_dir, source_name, project)
                    untrusted_projects.append(project)

        return config_projects, untrusted_projects

    @staticmethod
    def _loadTenantInRepoLayouts(merger, connections, config_projects,
                                 untrusted_projects, cached):
        config_projects_config = model.UnparsedTenantConfig()
        untrusted_projects_config = model.UnparsedTenantConfig()
        jobs = []

        for project in config_projects:
            # If we have cached data (this is a reconfiguration) use it.
            if cached and project.unparsed_config:
                TenantParser.log.info(
                    "Loading previously parsed configuration from %s" %
                    (project,))
                config_projects_config.extend(project.unparsed_config)
                continue
            # Otherwise, prepare an empty unparsed config object to
            # hold cached data later.
            project.unparsed_config = model.UnparsedTenantConfig()
            # Get main config files.  These files are permitted the
            # full range of configuration.
            job = merger.getFiles(
                project.source.connection.connection_name,
                project.name, 'master',
                files=['zuul.yaml', '.zuul.yaml'],
                dirs=['zuul.d', '.zuul.d'])
            job.source_context = model.SourceContext(project, 'master',
                                                     '', True)
            jobs.append(job)

        for project in untrusted_projects:
            # If we have cached data (this is a reconfiguration) use it.
            if cached and project.unparsed_config:
                TenantParser.log.info(
                    "Loading previously parsed configuration from %s" %
                    (project,))
                untrusted_projects_config.extend(project.unparsed_config)
                continue
            # Otherwise, prepare an empty unparsed config object to
            # hold cached data later.
            project.unparsed_config = model.UnparsedTenantConfig()
            # Get in-project-repo config files which have a restricted
            # set of options.
            # For each branch in the repo, get the zuul.yaml for that
            # branch.  Remember the branch and then implicitly add a
            # branch selector to each job there.  This makes the
            # in-repo configuration apply only to that branch.
            for branch in project.source.getProjectBranches(project):
                project.unparsed_branch_config[branch] = \
                    model.UnparsedTenantConfig()
                job = merger.getFiles(
                    project.source.connection.connection_name,
                    project.name, branch,
                    files=['.zuul.yaml'],
                    dirs=['.zuul.d'])
                job.source_context = model.SourceContext(
                    project, branch, '', False)
                jobs.append(job)

        for job in jobs:
            # Note: this is an ordered list -- we wait for cat jobs to
            # complete in the order they were executed which is the
            # same order they were defined in the main config file.
            # This is important for correct inheritance.
            TenantParser.log.debug("Waiting for cat job %s" % (job,))
            job.wait()
            TenantParser.log.debug("Cat job finished! %s" % (job.files,))
            loaded = False
            for fn in ['zuul.yaml', '.zuul.yaml']:
                if job.files.get(fn):
                    # Don't load from more than one file in a repo-branch
                    if loaded:
                        TenantParser.log.warning(
                            "Multiple configuration files in %s" %
                            (job.source_context,))
                        continue
                    loaded = True
                    job.source_context.path = fn
                    TenantParser.log.info(
                        "Loading configuration from %s" %
                        (job.source_context,))
                    project = job.source_context.project
                    branch = job.source_context.branch
                    if job.source_context.trusted:
                        incdata = TenantParser._parseConfigProjectLayout(
                            job.files[fn], job.source_context)
                        config_projects_config.extend(incdata)
                    else:
                        incdata = TenantParser._parseUntrustedProjectLayout(
                            job.files[fn], job.source_context)
                        untrusted_projects_config.extend(incdata)
                    project.unparsed_config.extend(incdata)
                    if branch in project.unparsed_branch_config:
                        project.unparsed_branch_config[branch].extend(incdata)
            loaded = False
            files = sorted(job.files.keys())
            for dn in ['zuul.d', '.zuul.d']:
                for fn in files:
                    if not fn.startswith("%s/" % dn):
                        continue
                    if loaded and loaded != dn:
                        TenantParser.log.warning(
                            "Multiple configuration directories in %s" %
                            (job.source_context,))
                        continue
                    loaded = dn
                    job.source_context.path = fn
                    TenantParser.log.info(
                        "Loading configuration from %s" %
                        (job.source_context,))
                    project = job.source_context.project
                    branch = job.source_context.branch
                    if job.source_context.trusted:
                        incdata = TenantParser._parseConfigProjectLayout(
                            job.files[fn], job.source_context)
                        config_projects_config.extend(incdata)
                    else:
                        incdata = TenantParser._parseUntrustedProjectLayout(
                            job.files[fn], job.source_context)
                        untrusted_projects_config.extend(incdata)
                    project.unparsed_config.extend(incdata)
                    if branch in project.unparsed_branch_config:
                        project.unparsed_branch_config[branch].extend(incdata)
        return config_projects_config, untrusted_projects_config

    @staticmethod
    def _parseConfigProjectLayout(data, source_context):
        # This is the top-level configuration for a tenant.
        config = model.UnparsedTenantConfig()
        config.extend(safe_load_yaml(data, source_context))
        return config

    @staticmethod
    def _parseUntrustedProjectLayout(data, source_context):
        config = model.UnparsedTenantConfig()
        config.extend(safe_load_yaml(data, source_context))
        if config.pipelines:
            with configuration_exceptions('pipeline', config.pipelines[0]):
                raise PipelineNotPermittedError()
        return config

    @staticmethod
    def _parseLayoutItems(layout, tenant, data, scheduler, connections,
                          skip_pipelines=False, skip_semaphores=False):
        if not skip_pipelines:
            for config_pipeline in data.pipelines:
                classes = config_pipeline['_source_context'].\
                    project.load_classes
                if 'pipeline' not in classes:
                    continue
                layout.addPipeline(PipelineParser.fromYaml(
                    layout, connections,
                    scheduler, config_pipeline))

        for config_nodeset in data.nodesets:
            classes = config_nodeset['_source_context'].project.load_classes
            if 'nodeset' not in classes:
                continue
            with configuration_exceptions('nodeset', config_nodeset):
                layout.addNodeSet(NodeSetParser.fromYaml(
                    layout, config_nodeset))

        for config_secret in data.secrets:
            classes = config_secret['_source_context'].project.load_classes
            if 'secret' not in classes:
                continue
            layout.addSecret(SecretParser.fromYaml(layout, config_secret))

        for config_job in data.jobs:
            classes = config_job['_source_context'].project.load_classes
            if 'job' not in classes:
                continue
            with configuration_exceptions('job', config_job):
                job = JobParser.fromYaml(tenant, layout, config_job)
                layout.addJob(job)

        if not skip_semaphores:
            for config_semaphore in data.semaphores:
                classes = config_semaphore['_source_context'].\
                    project.load_classes
                if 'semaphore' not in classes:
                    continue
                layout.addSemaphore(SemaphoreParser.fromYaml(config_semaphore))

        for config_template in data.project_templates:
            classes = config_template['_source_context'].project.load_classes
            if 'project-template' not in classes:
                continue
            layout.addProjectTemplate(ProjectTemplateParser.fromYaml(
                tenant, layout, config_template))

        for config_projects in data.projects.values():
            # Unlike other config classes, we expect multiple project
            # stanzas with the same name, so that a config repo can
            # define a project-pipeline and the project itself can
            # augment it.  To that end, config_project is a list of
            # each of the project stanzas.  Each one may be (should
            # be!) from a different repo, so filter them according to
            # the include/exclude rules before parsing them.
            filtered_projects = [
                p for p in config_projects if
                'project' in p['_source_context'].project.load_classes
            ]

            if not filtered_projects:
                continue

            layout.addProjectConfig(ProjectParser.fromYaml(
                tenant, layout, filtered_projects))

    @staticmethod
    def _parseLayout(base, tenant, data, scheduler, connections):
        layout = model.Layout()

        TenantParser._parseLayoutItems(layout, tenant, data,
                                       scheduler, connections)

        layout.tenant = tenant

        for pipeline in layout.pipelines.values():
            pipeline.manager._postConfig(layout)

        return layout


class ConfigLoader(object):
    log = logging.getLogger("zuul.ConfigLoader")

    def expandConfigPath(self, config_path):
        if config_path:
            config_path = os.path.expanduser(config_path)
        if not os.path.exists(config_path):
            raise Exception("Unable to read tenant config file at %s" %
                            config_path)
        return config_path

    def loadConfig(self, config_path, project_key_dir, scheduler, merger,
                   connections):
        abide = model.Abide()

        config_path = self.expandConfigPath(config_path)
        with open(config_path) as config_file:
            self.log.info("Loading configuration from %s" % (config_path,))
            data = yaml.safe_load(config_file)
        config = model.UnparsedAbideConfig()
        config.extend(data)
        base = os.path.dirname(os.path.realpath(config_path))

        for conf_tenant in config.tenants:
            # When performing a full reload, do not use cached data.
            tenant = TenantParser.fromYaml(
                base, project_key_dir, connections, scheduler, merger,
                conf_tenant, cached=False)
            abide.tenants[tenant.name] = tenant
        return abide

    def reloadTenant(self, config_path, project_key_dir, scheduler,
                     merger, connections, abide, tenant):
        new_abide = model.Abide()
        new_abide.tenants = abide.tenants.copy()

        config_path = self.expandConfigPath(config_path)
        base = os.path.dirname(os.path.realpath(config_path))

        # When reloading a tenant only, use cached data if available.
        new_tenant = TenantParser.fromYaml(
            base, project_key_dir, connections, scheduler, merger,
            tenant.unparsed_config, cached=True)
        new_abide.tenants[tenant.name] = new_tenant
        return new_abide

    def _loadDynamicProjectData(self, config, project, files, trusted):
        fns = []
        if trusted:
            branches = ['master']
            files_list = files.connections.get(
                project.source.connection.connection_name, {}).get(
                    project.name, {}).get('master', {}).keys()
            for fn in files_list:
                if fn.startswith("zuul.d/"):
                    fns.append(fn)
            fns.sort()
            fns.insert(0, 'zuul.yaml')
        else:
            branches = project.source.getProjectBranches(project)
            for branch in branches:
                files_list = files.connections.get(
                    project.source.connection.connection_name, {}).get(
                        project.name, {}).get(branch, {}).keys()
                for fn in files_list:
                    if fn.startswith(".zuul.d/"):
                        fns.append(fn)
            fns.sort()
            fns.insert(0, '.zuul.yaml')

        for branch in branches:
            for fn in fns:
                incdata = None
                data = files.getFile(project.source.connection.connection_name,
                                     project.name, branch, fn)
                if data:
                    source_context = model.SourceContext(project, branch,
                                                         fn, trusted)
                    if trusted:
                        incdata = TenantParser._parseConfigProjectLayout(
                            data, source_context)
                    else:
                        incdata = TenantParser._parseUntrustedProjectLayout(
                            data, source_context)
                else:
                    if trusted:
                        incdata = project.unparsed_config
                    else:
                        incdata = project.unparsed_branch_config.get(branch)
                if incdata:
                    config.extend(incdata)

    def createDynamicLayout(self, tenant, files,
                            include_config_projects=False):
        if include_config_projects:
            config = model.UnparsedTenantConfig()
            for project in tenant.config_projects:
                self._loadDynamicProjectData(config, project, files, True)
        else:
            config = tenant.config_projects_config.copy()
        for project in tenant.untrusted_projects:
            self._loadDynamicProjectData(config, project, files, False)

        layout = model.Layout()
        # NOTE: the actual pipeline objects (complete with queues and
        # enqueued items) are copied by reference here.  This allows
        # our shadow dynamic configuration to continue to interact
        # with all the other changes, each of which may have their own
        # version of reality.  We do not support creating, updating,
        # or deleting pipelines in dynamic layout changes.
        layout.pipelines = tenant.layout.pipelines

        # NOTE: the semaphore definitions are copied from the static layout
        # here. For semaphores there should be no per patch max value but
        # exactly one value at any time. So we do not support dynamic semaphore
        # configuration changes.
        layout.semaphores = tenant.layout.semaphores

        TenantParser._parseLayoutItems(layout, tenant, config, None, None,
                                       skip_pipelines=True,
                                       skip_semaphores=True)

        return layout
