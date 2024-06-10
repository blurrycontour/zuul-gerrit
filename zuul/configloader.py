# Copyright 2023 Acme Gating, LLC
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

import collections
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import io
import itertools
import logging
import math
import os
import re
import re2
import subprocess
import textwrap
import threading
import types

import voluptuous as vs

from zuul import change_matcher
from zuul import model
from zuul.connection import ReadOnlyBranchCacheError
from zuul.lib import yamlutil as yaml
import zuul.manager.dependent
import zuul.manager.independent
import zuul.manager.supercedent
import zuul.manager.serial
from zuul.lib.logutil import get_annotated_logger
from zuul.lib.re2util import filter_allowed_disallowed, ZuulRegex
from zuul.lib.varnames import check_varnames
from zuul.zk.components import COMPONENT_REGISTRY
from zuul.zk.semaphore import SemaphoreHandler
from zuul.exceptions import (
    SEVERITY_ERROR,
    DuplicateGroupError,
    DuplicateNodeError,
    GlobalSemaphoreNotFoundError,
    LabelForbiddenError,
    MaxTimeoutError,
    MultipleProjectConfigurations,
    NodeFromGroupNotFoundError,
    PipelineNotPermittedError,
    ProjectNotFoundError,
    ProjectNotPermittedError,
    RegexDeprecation,
    TemplateNotFoundError,
    UnknownConnection,
    YAMLDuplicateKeyError,
)

ZUUL_CONF_ROOT = ('zuul.yaml', 'zuul.d', '.zuul.yaml', '.zuul.d')

# A voluptuous schema for a regular expression.
ZUUL_REGEX = {
    vs.Required('regex'): str,
    'negate': bool,
}


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


def no_dup_config_paths(v):
    if isinstance(v, list):
        for x in v:
            check_config_path(x)
    elif isinstance(v, str):
        check_config_path(v)
    else:
        raise vs.Invalid("Expected str or list of str for extra-config-paths")


def check_config_path(path):
    if not isinstance(path, str):
        raise vs.Invalid("Expected str or list of str for extra-config-paths")
    elif path in ["zuul.yaml", "zuul.d/", ".zuul.yaml", ".zuul.d/"]:
        raise vs.Invalid("Default zuul configs are not "
                         "allowed in extra-config-paths")


def make_regex(data, parse_context=None):
    if isinstance(data, dict):
        regex = ZuulRegex(data['regex'],
                          negate=data.get('negate', False))
    else:
        regex = ZuulRegex(data)
    if parse_context and regex.re2_failure:
        if regex.re2_failure_message:
            parse_context.accumulator.addError(RegexDeprecation(
                regex.re2_failure_message))
        else:
            parse_context.accumulator.addError(RegexDeprecation())
    return regex


def indent(s):
    return '\n'.join(['  ' + x for x in s.split('\n')])


class LocalAccumulator:
    """An error accumulator that wraps another accumulator (like
    LoadingErrors) while holding local context information.
    """
    def __init__(self, accumulator, source_context=None, stanza=None,
                 conf=None, attr=None):
        self.accumulator = accumulator
        self.source_context = source_context
        self.stanza = stanza
        self.conf = conf
        self.attr = attr

    def extend(self, source_context=None, stanza=None,
               conf=None, attr=None):
        """Return a new accumulator that extends this one with additional
        info"""
        if conf:
            if isinstance(conf, (types.MappingProxyType, dict)):
                conf_context = conf.get('_source_context')
            else:
                conf_context = getattr(conf, 'source_context', None)
            source_context = source_context or conf_context
        return LocalAccumulator(self.accumulator,
                                source_context or self.source_context,
                                stanza or self.stanza,
                                conf or self.conf,
                                attr or self.attr)

    @contextmanager
    def catchErrors(self):
        try:
            yield
        except ReadOnlyBranchCacheError:
            raise
        except Exception as exc:
            self.addError(exc)

    def addError(self, error):
        """Adds the error or warning to the accumulator.

        The input can be any exception or any object with the
        zuul_error attributes.

        If the error has a source_context or start_mark attribute,
        this method will use those.

        This method will produce the most detailed error message it
        can with the data supplied by the error and the most recent
        error context.
        """

        # A list of paragraphs
        msg = []

        repo = branch = None

        source_context = getattr(error, 'source_context', self.source_context)
        if source_context:
            repo = source_context.project_name
            branch = source_context.branch
        stanza = self.stanza

        problem = getattr(error, 'zuul_error_problem', 'syntax error')
        if problem[0] in 'aoeui':
            a_an = 'an'
        else:
            a_an = 'a'

        if repo and branch:
            intro = f"""\
            Zuul encountered {a_an} {problem} while parsing its
            configuration in the repo {repo} on branch {branch}.  The
            problem was:"""
        elif repo:
            intro = f"""\
            Zuul encountered an error while accessing the repo {repo}.
            The error was:"""
        else:
            intro = "Zuul encountered an error:"

        msg.append(textwrap.dedent(intro))

        error_text = getattr(error, 'zuul_error_message', str(error))
        msg.append(indent(error_text))

        snippet = start_mark = name = line = location = None
        attr = self.attr
        if self.conf:
            if isinstance(self.conf, (types.MappingProxyType, dict)):
                name = self.conf.get('name')
                start_mark = self.conf.get('_start_mark')
            else:
                name = getattr(self.conf, 'name', None)
                start_mark = getattr(self.conf, 'start_mark', None)
        if start_mark is None:
            start_mark = getattr(error, 'start_mark', None)
        if start_mark:
            line = start_mark.line
            if attr is not None:
                line = getattr(attr, 'line', line)
            snippet = start_mark.getLineSnippet(line).rstrip()
            location = start_mark.getLineLocation(line)
        if name:
            name = f'"{name}"'
        else:
            name = 'following'
        if stanza:
            if attr is not None:
                pointer = (
                    f'The problem appears in the "{attr}" attribute\n'
                    f'of the {name} {stanza} stanza:'
                )
            else:
                pointer = (
                    f'The problem appears in the the {name} {stanza} stanza:'
                )
            msg.append(pointer)

        if snippet:
            msg.append(indent(snippet))
        if location:
            msg.append(location)

        error_message = '\n\n'.join(msg)
        error_severity = getattr(error, 'zuul_error_severity',
                                 SEVERITY_ERROR)
        error_name = getattr(error, 'zuul_error_name', 'Unknown')

        config_error = model.ConfigurationError(
            source_context, start_mark, error_message,
            short_error=error_text,
            severity=error_severity,
            name=error_name)
        self.accumulator.addError(config_error)


class ZuulSafeLoader(yaml.EncryptedLoader):
    zuul_node_types = frozenset(('job', 'nodeset', 'secret', 'pipeline',
                                 'project', 'project-template',
                                 'semaphore', 'queue', 'pragma'))

    def __init__(self, stream, source_context):
        wrapped_stream = io.StringIO(stream)
        wrapped_stream.name = str(source_context)
        super(ZuulSafeLoader, self).__init__(wrapped_stream)
        self.name = str(source_context)
        self.zuul_context = source_context
        self.zuul_stream = stream

    def construct_mapping(self, node, deep=False):
        keys = set()
        for k, v in node.value:
            # The key << needs to be treated special since that will merge
            # the anchor into the mapping and not create a key on its own.
            if k.value == '<<':
                continue

            if not isinstance(k.value, collections.abc.Hashable):
                # This happens with "foo: {{ bar }}"
                # This will raise an error in the superclass
                # construct_mapping below; ignore it for now.
                continue

            if k.value in keys:
                mark = model.ZuulMark(node.start_mark, node.end_mark,
                                      self.zuul_stream)
                raise YAMLDuplicateKeyError(k.value, self.zuul_context,
                                            mark)
            keys.add(k.value)
            if k.tag == 'tag:yaml.org,2002:str':
                k.value = yaml.ZuulConfigKey(k.value, node.start_mark.line)
        r = super(ZuulSafeLoader, self).construct_mapping(node, deep)
        keys = frozenset(r.keys())
        if len(keys) == 1 and keys.intersection(self.zuul_node_types):
            d = list(r.values())[0]
            if isinstance(d, dict):
                d['_start_mark'] = model.ZuulMark(node.start_mark,
                                                  node.end_mark,
                                                  self.zuul_stream)
                d['_source_context'] = self.zuul_context
        return r


def safe_load_yaml(stream, source_context):
    loader = ZuulSafeLoader(stream, source_context)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def ansible_var_name(value):
    vs.Schema(str)(value)
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", value):
        raise vs.Invalid("Invalid Ansible variable name '{}'".format(value))


def ansible_vars_dict(value):
    vs.Schema(dict)(value)
    for key in value:
        ansible_var_name(key)


def copy_safe_config(conf):
    """Return a deep copy of a config dictionary.

    This lets us assign values of a config dictionary to configuration
    objects, even if those values are nested dictionaries.  This way
    we can safely freeze the configuration object (the process of
    which mutates dictionaries) without mutating the original
    configuration.

    Meanwhile, this does retain the original context information as a
    single object (some behaviors rely on mutating the source context
    (e.g., pragma)).

    """
    ret = copy.deepcopy(conf)
    for key in (
            '_source_context',
            '_start_mark',
    ):
        if key in conf:
            ret[key] = conf[key]
    return ret


class PragmaParser(object):
    pragma = {
        'implied-branch-matchers': bool,
        'implied-branches': to_list(vs.Any(ZUUL_REGEX, str)),
        '_source_context': model.SourceContext,
        '_start_mark': model.ZuulMark,
    }

    schema = vs.Schema(pragma)

    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.PragmaParser")
        self.pcontext = pcontext

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        bm = conf.get('implied-branch-matchers')

        source_context = conf['_source_context']
        if bm is not None:
            source_context.implied_branch_matchers = bm

        with self.pcontext.confAttr(conf, 'implied-branches') as branches:
            if branches is not None:
                # This is a BranchMatcher (not an ImpliedBranchMatcher)
                # because as user input, we allow/expect this to be
                # regular expressions.  Only truly implicit branch names
                # (automatically generated from source file branches) are
                # ImpliedBranchMatchers.
                source_context.implied_branches = [
                    change_matcher.BranchMatcher(make_regex(x, self.pcontext))
                    for x in as_list(branches)]


class NodeSetParser(object):
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.NodeSetParser")
        self.pcontext = pcontext
        self.anonymous = False
        self.schema = self.getSchema(False)
        self.anon_schema = self.getSchema(True)

    def getSchema(self, anonymous=False):
        node = {vs.Required('name'): to_list(str),
                vs.Required('label'): str,
                }

        group = {vs.Required('name'): str,
                 vs.Required('nodes'): to_list(str),
                 }

        real_nodeset = {vs.Required('nodes'): to_list(node),
                        'groups': to_list(group),
                        }

        alt_nodeset = {vs.Required('alternatives'):
                       [vs.Any(real_nodeset, str)]}

        top_nodeset = {'_source_context': model.SourceContext,
                       '_start_mark': model.ZuulMark,
                       }
        if not anonymous:
            top_nodeset[vs.Required('name')] = str

        top_real_nodeset = real_nodeset.copy()
        top_real_nodeset.update(top_nodeset)
        top_alt_nodeset = alt_nodeset.copy()
        top_alt_nodeset.update(top_nodeset)

        nodeset = vs.Any(top_real_nodeset, top_alt_nodeset)

        return vs.Schema(nodeset)

    def fromYaml(self, conf, anonymous=False):
        conf = copy_safe_config(conf)
        if anonymous:
            self.anon_schema(conf)
            self.anonymous = True
        else:
            self.schema(conf)

        if 'alternatives' in conf:
            return self.loadAlternatives(conf)
        else:
            return self.loadNodeset(conf)

    def loadAlternatives(self, conf):
        ns = model.NodeSet(conf.get('name'))
        ns.source_context = conf.get('_source_context')
        ns.start_mark = conf.get('_start_mark')
        for alt in conf['alternatives']:
            if isinstance(alt, str):
                ns.addAlternative(alt)
            else:
                ns.addAlternative(self.loadNodeset(alt))
        return ns

    def loadNodeset(self, conf):
        ns = model.NodeSet(conf.get('name'))
        ns.source_context = conf.get('_source_context')
        ns.start_mark = conf.get('_start_mark')
        node_names = set()
        group_names = set()
        allowed_labels = self.pcontext.tenant.allowed_labels
        disallowed_labels = self.pcontext.tenant.disallowed_labels

        requested_labels = [n['label'] for n in as_list(conf['nodes'])]
        filtered_labels = filter_allowed_disallowed(
            requested_labels, allowed_labels, disallowed_labels)
        rejected_labels = set(requested_labels) - set(filtered_labels)
        for name in rejected_labels:
            raise LabelForbiddenError(
                label=name,
                allowed_labels=allowed_labels,
                disallowed_labels=disallowed_labels)
        for conf_node in as_list(conf['nodes']):
            if "localhost" in as_list(conf_node['name']):
                raise Exception("Nodes named 'localhost' are not allowed.")
            for name in as_list(conf_node['name']):
                if name in node_names:
                    raise DuplicateNodeError(name, conf_node['name'])
            node = model.Node(as_list(conf_node['name']), conf_node['label'])
            ns.addNode(node)
            for name in as_list(conf_node['name']):
                node_names.add(name)
        for conf_group in as_list(conf.get('groups', [])):
            if "localhost" in conf_group['name']:
                raise Exception("Groups named 'localhost' are not allowed.")
            for node_name in as_list(conf_group['nodes']):
                if node_name not in node_names:
                    nodeset_str = 'the nodeset' if self.anonymous else \
                        'the nodeset "%s"' % conf['name']
                    raise NodeFromGroupNotFoundError(nodeset_str, node_name,
                                                     conf_group['name'])
            if conf_group['name'] in group_names:
                nodeset_str = 'the nodeset' if self.anonymous else \
                    'the nodeset "%s"' % conf['name']
                raise DuplicateGroupError(nodeset_str, conf_group['name'])
            group = model.Group(conf_group['name'],
                                as_list(conf_group['nodes']))
            ns.addGroup(group)
            group_names.add(conf_group['name'])
        ns.freeze()
        return ns


class SecretParser(object):
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.SecretParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()

    def getSchema(self):
        secret = {vs.Required('name'): str,
                  vs.Required('data'): dict,
                  '_source_context': model.SourceContext,
                  '_start_mark': model.ZuulMark,
                  }

        return vs.Schema(secret)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        s = model.Secret(conf['name'], conf['_source_context'])
        s.source_context = conf['_source_context']
        s.start_mark = conf['_start_mark']
        s.secret_data = conf['data']
        s.freeze()
        return s


class JobParser(object):
    ANSIBLE_ROLE_RE = re.compile(r'^(ansible[-_.+]*)*(role[-_.+]*)*')

    zuul_role = {vs.Required('zuul'): str,
                 'name': str}

    galaxy_role = {vs.Required('galaxy'): str,
                   'name': str}

    role = vs.Any(zuul_role, galaxy_role)

    job_project = {vs.Required('name'): str,
                   'override-branch': str,
                   'override-checkout': str}

    job_dependency = {vs.Required('name'): str,
                      'soft': bool}

    secret = {vs.Required('name'): ansible_var_name,
              vs.Required('secret'): str,
              'pass-to-parent': bool}

    semaphore = {vs.Required('name'): str,
                 'resources-first': bool}

    complex_playbook_def = {vs.Required('name'): str,
                            'semaphores': to_list(str)}

    playbook_def = to_list(vs.Any(str, complex_playbook_def))

    # Attributes of a job that can also be used in Project and ProjectTemplate
    job_attributes = {'parent': vs.Any(str, None),
                      'final': bool,
                      'abstract': bool,
                      'protected': bool,
                      'intermediate': bool,
                      'requires': to_list(str),
                      'provides': to_list(str),
                      'failure-message': str,
                      'success-message': str,
                      # TODO: ignored, remove for v5
                      'failure-url': str,
                      # TODO: ignored, remove for v5
                      'success-url': str,
                      'hold-following-changes': bool,
                      'voting': bool,
                      'semaphore': vs.Any(semaphore, str),
                      'semaphores': to_list(vs.Any(semaphore, str)),
                      'tags': to_list(str),
                      'branches': to_list(vs.Any(ZUUL_REGEX, str)),
                      'files': to_list(vs.Any(ZUUL_REGEX, str)),
                      'secrets': to_list(vs.Any(secret, str)),
                      'irrelevant-files': to_list(vs.Any(ZUUL_REGEX, str)),
                      # validation happens in NodeSetParser
                      'nodeset': vs.Any(dict, str),
                      'timeout': int,
                      'post-timeout': int,
                      'attempts': int,
                      'pre-run': playbook_def,
                      'post-run': playbook_def,
                      'run': playbook_def,
                      'cleanup-run': playbook_def,
                      'ansible-split-streams': bool,
                      'ansible-version': vs.Any(str, float, int),
                      '_source_context': model.SourceContext,
                      '_start_mark': model.ZuulMark,
                      'roles': to_list(role),
                      'required-projects': to_list(vs.Any(job_project, str)),
                      'vars': ansible_vars_dict,
                      'extra-vars': ansible_vars_dict,
                      'host-vars': {str: ansible_vars_dict},
                      'group-vars': {str: ansible_vars_dict},
                      'dependencies': to_list(vs.Any(job_dependency, str)),
                      'allowed-projects': to_list(str),
                      'override-branch': str,
                      'override-checkout': str,
                      'description': str,
                      'variant-description': str,
                      'post-review': bool,
                      'match-on-config-updates': bool,
                      'workspace-scheme': vs.Any('golang', 'flat', 'unique'),
                      'deduplicate': vs.Any(bool, 'auto'),
                      'failure-output': to_list(str),
    }

    job_name = {vs.Required('name'): str}

    job = dict(collections.ChainMap(job_name, job_attributes))

    schema = vs.Schema(job)

    simple_attributes = [
        'final',
        'abstract',
        'protected',
        'intermediate',
        'timeout',
        'post-timeout',
        'workspace',
        'voting',
        'hold-following-changes',
        'attempts',
        'failure-message',
        'success-message',
        'override-branch',
        'override-checkout',
        'match-on-config-updates',
        'workspace-scheme',
        'deduplicate',
    ]

    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.JobParser")
        self.pcontext = pcontext

    def fromYaml(self, conf,
                 project_pipeline=False, name=None, validate=True):
        conf = copy_safe_config(conf)
        if validate:
            self.schema(conf)

        if name is None:
            name = conf['name']

        # NB: The default detection system in the Job class requires
        # that we always assign values directly rather than modifying
        # them (e.g., "job.run = ..." rather than
        # "job.run.append(...)").

        job = model.Job(name)
        job.description = conf.get('description')
        job.source_context = conf['_source_context']
        job.start_mark = conf['_start_mark']
        job.variant_description = conf.get(
            'variant-description', " ".join([
                str(x) for x in as_list(conf.get('branches'))
            ]))

        if project_pipeline and conf['_source_context'].trusted:
            # A config project has attached this job to a
            # project-pipeline.  In this case, we can ignore
            # allowed-projects -- the superuser has stated they want
            # it to run.  This can be useful to allow untrusted jobs
            # with secrets to be run in other untrusted projects.
            job.ignore_allowed_projects = True

        if 'parent' in conf:
            if conf['parent'] is not None:
                # Parent job is explicitly specified, so inherit from it.
                job.parent = conf['parent']
            else:
                # Parent is explicitly set as None, so user intends
                # this to be a base job.  That's only okay if we're in
                # a config project.
                if not conf['_source_context'].trusted:
                    raise Exception(
                        "Base jobs must be defined in config projects")
                job.parent = job.BASE_JOB_MARKER

        # Secrets are part of the playbook context so we must establish
        # them earlier than playbooks.
        secrets = []
        for secret_config in as_list(conf.get('secrets', [])):
            if isinstance(secret_config, str):
                secret_name = secret_config
                secret_alias = secret_config
                secret_ptp = False
            else:
                secret_name = secret_config['secret']
                secret_alias = secret_config['name']
                secret_ptp = secret_config.get('pass-to-parent', False)
            secret_use = model.SecretUse(secret_name, secret_alias)
            secret_use.pass_to_parent = secret_ptp
            secrets.append(secret_use)
        job.secrets = tuple(secrets)

        # A job in an untrusted repo that uses secrets requires
        # special care.  We must note this, and carry this flag
        # through inheritance to ensure that we don't run this job in
        # an unsafe check pipeline.  We must also set allowed-projects
        # to only the current project, as otherwise, other projects
        # might be able to cause something to happen with the secret
        # by using a depends-on header.
        if secrets and not conf['_source_context'].trusted:
            job.post_review = True
            job.allowed_projects = frozenset((
                conf['_source_context'].project_name,))

        if (conf.get('timeout') and
            self.pcontext.tenant.max_job_timeout != -1 and
            int(conf['timeout']) > self.pcontext.tenant.max_job_timeout):
            raise MaxTimeoutError(job, self.pcontext.tenant)

        if (conf.get('post-timeout') and
            self.pcontext.tenant.max_job_timeout != -1 and
            int(conf['post-timeout']) > self.pcontext.tenant.max_job_timeout):
            raise MaxTimeoutError(job, self.pcontext.tenant)

        if 'post-review' in conf:
            if conf['post-review']:
                job.post_review = True
            else:
                raise Exception("Once set, the post-review attribute "
                                "may not be unset")

        job.ansible_split_streams = conf.get('ansible-split-streams')

        # Configure and validate ansible version
        if 'ansible-version' in conf:
            # The ansible-version can be treated by yaml as a float or
            # int so convert it to a string.
            ansible_version = str(conf['ansible-version'])
            self.pcontext.ansible_manager.requestVersion(ansible_version)
            job.ansible_version = ansible_version

        # Roles are part of the playbook context so we must establish
        # them earlier than playbooks.
        roles = []
        if 'roles' in conf:
            for role in conf.get('roles', []):
                if 'zuul' in role:
                    r = self._makeZuulRole(job, role)
                    if r:
                        roles.append(r)
        # A job's repo should be an implicit role source for that job,
        # but not in a project-pipeline variant.
        if not project_pipeline:
            r = self._makeImplicitRole(job)
            roles.insert(0, r)
        job.addRoles(roles)

        seen_playbook_semaphores = set()

        def get_playbook_attrs(playbook_defs):
            # Helper method to extract information from a playbook
            # defenition.
            for pb_def in playbook_defs:
                pb_semaphores = []
                if isinstance(pb_def, dict):
                    pb_name = pb_def['name']
                    for pb_sem_name in as_list(pb_def.get('semaphores')):
                        pb_semaphores.append(model.JobSemaphore(pb_sem_name))
                        seen_playbook_semaphores.add(pb_sem_name)
                else:
                    # The playbook definition is a simple string path
                    pb_name = pb_def
                # Sort the list of semaphores to avoid issues with
                # contention (where two jobs try to start at the same time
                # and fail due to acquiring the same semaphores but in
                # reverse order.
                pb_semaphores = tuple(sorted(pb_semaphores,
                                             key=lambda x: x.name))
                yield (pb_name, pb_semaphores)

        for pre_run_name, pre_run_semaphores in get_playbook_attrs(
                as_list(conf.get('pre-run'))):
            pre_run = model.PlaybookContext(job.source_context,
                                            pre_run_name, job.roles,
                                            secrets, pre_run_semaphores)
            job.pre_run = job.pre_run + (pre_run,)
        # NOTE(pabelanger): Reverse the order of our post-run list. We prepend
        # post-runs for inherits however, we want to execute post-runs in the
        # order they are listed within the job.
        for post_run_name, post_run_semaphores in get_playbook_attrs(
                reversed(as_list(conf.get('post-run')))):
            post_run = model.PlaybookContext(job.source_context,
                                             post_run_name, job.roles,
                                             secrets, post_run_semaphores)
            job.post_run = (post_run,) + job.post_run
        for cleanup_run_name, cleanup_run_semaphores in get_playbook_attrs(
                reversed(as_list(conf.get('cleanup-run')))):
            cleanup_run = model.PlaybookContext(
                job.source_context,
                cleanup_run_name, job.roles,
                secrets, cleanup_run_semaphores)
            job.cleanup_run = (cleanup_run,) + job.cleanup_run

        if 'run' in conf:
            for run_name, run_semaphores in get_playbook_attrs(
                    as_list(conf.get('run'))):
                run = model.PlaybookContext(job.source_context, run_name,
                                            job.roles, secrets, run_semaphores)
                job.run = job.run + (run,)

        if conf.get('intermediate', False) and not conf.get('abstract', False):
            raise Exception("An intermediate job must also be abstract")

        for k in self.simple_attributes:
            a = k.replace('-', '_')
            if k in conf:
                setattr(job, a, conf[k])
        if 'nodeset' in conf:
            conf_nodeset = conf['nodeset']
            if isinstance(conf_nodeset, str):
                # This references an existing named nodeset in the
                # layout; it will be validated later.
                ns = conf_nodeset
            else:
                ns = self.pcontext.nodeset_parser.fromYaml(
                    conf_nodeset, anonymous=True)
            job.nodeset = ns

        if 'required-projects' in conf:
            new_projects = {}
            projects = as_list(conf.get('required-projects', []))
            unknown_projects = []
            for project in projects:
                if isinstance(project, dict):
                    project_name = project['name']
                    project_override_branch = project.get('override-branch')
                    project_override_checkout = project.get(
                        'override-checkout')
                else:
                    project_name = project
                    project_override_branch = None
                    project_override_checkout = None
                (trusted, project) = self.pcontext.tenant.getProject(
                    project_name)
                if project is None:
                    unknown_projects.append(project_name)
                    continue
                job_project = model.JobProject(project.canonical_name,
                                               project_override_branch,
                                               project_override_checkout)
                new_projects[project.canonical_name] = job_project

            # NOTE(mnaser): We accumulate all unknown projects and throw an
            #               exception only once to capture all of them in the
            #               error message.
            if unknown_projects:
                raise ProjectNotFoundError(unknown_projects)

            job.required_projects = new_projects

        if 'dependencies' in conf:
            new_dependencies = []
            dependencies = as_list(conf.get('dependencies', []))
            for dep in dependencies:
                if isinstance(dep, dict):
                    dep_name = dep['name']
                    dep_soft = dep.get('soft', False)
                else:
                    dep_name = dep
                    dep_soft = False
                job_dependency = model.JobDependency(dep_name, dep_soft)
                new_dependencies.append(job_dependency)
            job.dependencies = new_dependencies

        semaphores = as_list(conf.get('semaphores', conf.get('semaphore', [])))
        job_semaphores = []
        for semaphore in semaphores:
            if isinstance(semaphore, str):
                job_semaphores.append(model.JobSemaphore(semaphore))
            else:
                job_semaphores.append(model.JobSemaphore(
                    semaphore.get('name'),
                    semaphore.get('resources-first', False)))

        if job_semaphores:
            # Sort the list of semaphores to avoid issues with
            # contention (where two jobs try to start at the same time
            # and fail due to acquiring the same semaphores but in
            # reverse order.
            job.semaphores = tuple(sorted(job_semaphores,
                                          key=lambda x: x.name))
            common = (set([x.name for x in job_semaphores]) &
                      seen_playbook_semaphores)
            if common:
                raise Exception(f"Semaphores {common} specified as both "
                                "job and playbook semaphores but may only "
                                "be used for one")

        for k in ('tags', 'requires', 'provides'):
            v = frozenset(as_list(conf.get(k)))
            if v:
                setattr(job, k, v)

        variables = conf.get('vars', None)
        if variables:
            check_varnames(variables)
            job.variables = variables
        extra_variables = conf.get('extra-vars', None)
        if extra_variables:
            check_varnames(extra_variables)
            job.extra_variables = extra_variables
        host_variables = conf.get('host-vars', None)
        if host_variables:
            for host, hvars in host_variables.items():
                check_varnames(hvars)
            job.host_variables = host_variables
        group_variables = conf.get('group-vars', None)
        if group_variables:
            for group, gvars in group_variables.items():
                check_varnames(gvars)
            job.group_variables = group_variables

        allowed_projects = conf.get('allowed-projects', None)
        # See note above at "post-review".
        if allowed_projects and not job.allowed_projects:
            allowed = []
            for p in as_list(allowed_projects):
                (trusted, project) = self.pcontext.tenant.getProject(p)
                if project is None:
                    raise ProjectNotFoundError(p)
                allowed.append(project.name)
            job.allowed_projects = frozenset(allowed)

        branches = None
        if 'branches' in conf:
            with self.pcontext.confAttr(conf, 'branches') as conf_branches:
                branches = [
                    change_matcher.BranchMatcher(
                        make_regex(x, self.pcontext))
                    for x in as_list(conf_branches)
                ]
        elif not project_pipeline:
            branches = self.pcontext.getImpliedBranches(job.source_context)
        if branches:
            job.setBranchMatcher(branches)
        if 'files' in conf:
            with self.pcontext.confAttr(conf, 'files') as conf_files:
                job.setFileMatcher([
                    make_regex(x, self.pcontext)
                    for x in as_list(conf_files)
                ])
        if 'irrelevant-files' in conf:
            with self.pcontext.confAttr(conf,
                                        'irrelevant-files') as conf_ifiles:
                job.setIrrelevantFileMatcher([
                    make_regex(x, self.pcontext)
                    for x in as_list(conf_ifiles)
                ])
        if 'failure-output' in conf:
            failure_output = as_list(conf['failure-output'])
            # Test compilation to detect errors, but the zuul_stream
            # callback plugin is what actually needs re objects, so we
            # let it recompile them later.
            for x in failure_output:
                re2.compile(x)
            job.failure_output = tuple(failure_output)

        job.freeze()
        return job

    def _makeZuulRole(self, job, role):
        name = role['zuul'].split('/')[-1]

        (trusted, project) = self.pcontext.tenant.getProject(role['zuul'])
        if project is None:
            return None

        return model.ZuulRole(role.get('name', name),
                              project.canonical_name)

    def _makeImplicitRole(self, job):
        project_name = job.source_context.project_name
        name = project_name.split('/')[-1]
        name = JobParser.ANSIBLE_ROLE_RE.sub('', name) or name
        return model.ZuulRole(name,
                              job.source_context.project_canonical_name,
                              implicit=True)


class ProjectTemplateParser(object):
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.ProjectTemplateParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()
        self.not_pipelines = ['name', 'description', 'templates',
                              'merge-mode', 'default-branch', 'vars',
                              'queue', '_source_context', '_start_mark']

    def getSchema(self):
        job = {str: vs.Any(str, JobParser.job_attributes)}
        job_list = [vs.Any(str, job)]

        pipeline_contents = {
            'debug': bool,
            'fail-fast': bool,
            'jobs': job_list
        }

        project = {
            'name': str,
            'description': str,
            'queue': str,
            'vars': ansible_vars_dict,
            str: pipeline_contents,
            '_source_context': model.SourceContext,
            '_start_mark': model.ZuulMark,
        }

        return vs.Schema(project)

    def fromYaml(self, conf, validate=True, freeze=True):
        conf = copy_safe_config(conf)
        if validate:
            self.schema(conf)
        source_context = conf['_source_context']
        start_mark = conf['_start_mark']
        project_template = model.ProjectConfig(conf.get('name'))
        project_template.source_context = conf['_source_context']
        project_template.start_mark = conf['_start_mark']
        project_template.is_template = True
        project_template.queue_name = conf.get('queue')
        for pipeline_name, conf_pipeline in conf.items():
            if pipeline_name in self.not_pipelines:
                continue
            project_pipeline = model.ProjectPipelineConfig()
            project_template.pipelines[pipeline_name] = project_pipeline
            project_pipeline.debug = conf_pipeline.get('debug')
            project_pipeline.fail_fast = conf_pipeline.get(
                'fail-fast')
            self.parseJobList(
                conf_pipeline.get('jobs', []),
                source_context, start_mark, project_pipeline.job_list)

        # If this project definition is in a place where it
        # should get implied branch matchers, set it.
        branches = self.pcontext.getImpliedBranches(source_context)
        if branches:
            project_template.setImpliedBranchMatchers(branches)

        variables = conf.get('vars', {})
        forbidden = {'zuul', 'nodepool', 'unsafe_vars'}
        if variables:
            if set(variables.keys()).intersection(forbidden):
                raise Exception("Variables named 'zuul', 'nodepool', "
                                "or 'unsafe_vars' are not allowed.")
            project_template.variables = variables

        if freeze:
            project_template.freeze()
        return project_template

    def parseJobList(self, conf, source_context, start_mark, job_list):
        for conf_job in conf:
            if isinstance(conf_job, str):
                jobname = conf_job
                attrs = {}
            elif isinstance(conf_job, dict):
                # A dictionary in a job tree may override params
                jobname, attrs = list(conf_job.items())[0]
            else:
                raise Exception("Job must be a string or dictionary")
            attrs['_source_context'] = source_context
            attrs['_start_mark'] = start_mark

            job_list.addJob(self.pcontext.job_parser.fromYaml(
                attrs, project_pipeline=True,
                name=jobname, validate=False))


class ProjectParser(object):
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.ProjectParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()

    def getSchema(self):
        job = {str: vs.Any(str, JobParser.job_attributes)}
        job_list = [vs.Any(str, job)]

        pipeline_contents = {
            'debug': bool,
            'fail-fast': bool,
            'jobs': job_list
        }

        project = {
            'name': str,
            'description': str,
            'vars': ansible_vars_dict,
            'templates': [str],
            'merge-mode': vs.Any('merge', 'merge-resolve',
                                 'cherry-pick', 'squash-merge',
                                 'rebase'),
            'default-branch': str,
            'queue': str,
            str: pipeline_contents,
            '_source_context': model.SourceContext,
            '_start_mark': model.ZuulMark,
        }

        return vs.Schema(project)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)

        project_name = conf.get('name')
        source_context = conf['_source_context']
        if not project_name:
            # There is no name defined so implicitly add the name
            # of the project where it is defined.
            project_name = (source_context.project_canonical_name)

        if project_name.startswith('^'):
            # regex matching is designed to match other projects so disallow
            # in untrusted contexts
            if not source_context.trusted:
                raise ProjectNotPermittedError()

            # Parse the project as a template since they're mostly the
            # same.
            project_config = self.pcontext.project_template_parser. \
                fromYaml(conf, validate=False, freeze=False)

            project_config.name = project_name
        else:
            (trusted, project) = self.pcontext.tenant.getProject(project_name)
            if project is None:
                raise ProjectNotFoundError(project_name)

            if not source_context.trusted:
                if project.canonical_name != \
                        source_context.project_canonical_name:
                    raise ProjectNotPermittedError()

            # Parse the project as a template since they're mostly the
            # same.
            project_config = self.pcontext.project_template_parser.\
                fromYaml(conf, validate=False, freeze=False)

            project_config.name = project.canonical_name

            # Explicitly override this to False since we're reusing the
            # project-template loading method which sets it True.
            project_config.is_template = False

            # Pragmas can cause templates to end up with implied
            # branch matchers for arbitrary branches, but project
            # stanzas should not.  They should either have the current
            # branch or no branch matcher.
            if source_context.trusted:
                project_config.setImpliedBranchMatchers([])
            else:
                project_config.setImpliedBranchMatchers(
                    [change_matcher.ImpliedBranchMatcher(
                        ZuulRegex(source_context.branch))])

        # Add templates
        for name in conf.get('templates', []):
            if name not in project_config.templates:
                project_config.templates.append(name)

        mode = conf.get('merge-mode')
        if mode is not None:
            project_config.merge_mode = model.MERGER_MAP[mode]

        default_branch = conf.get('default-branch')
        project_config.default_branch = default_branch

        project_config.queue_name = conf.get('queue', None)

        variables = conf.get('vars', {})
        forbidden = {'zuul', 'nodepool', 'unsafe_vars'}
        if variables:
            if set(variables.keys()).intersection(forbidden):
                raise Exception("Variables named 'zuul', 'nodepool', "
                                "or 'unsafe_vars' are not allowed.")
            project_config.variables = variables

        project_config.freeze()
        return project_config


class PipelineParser(object):
    # A set of reporter configuration keys to action mapping
    reporter_actions = {
        'enqueue': 'enqueue_actions',
        'start': 'start_actions',
        'success': 'success_actions',
        'failure': 'failure_actions',
        'merge-conflict': 'merge_conflict_actions',
        'config-error': 'config_error_actions',
        'no-jobs': 'no_jobs_actions',
        'disabled': 'disabled_actions',
        'dequeue': 'dequeue_actions',
    }

    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.PipelineParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()

    def getDriverSchema(self, dtype):
        methods = {
            'trigger': 'getTriggerSchema',
            'reporter': 'getReporterSchema',
            'require': 'getRequireSchema',
            'reject': 'getRejectSchema',
        }

        schema = {}
        # Add the configured connections as available layout options
        for connection_name, connection in \
            self.pcontext.connections.connections.items():
            method = getattr(connection.driver, methods[dtype], None)
            if method:
                schema[connection_name] = to_list(method())

        return schema

    def getSchema(self):
        manager = vs.Any('independent',
                         'dependent',
                         'serial',
                         'supercedent')

        precedence = vs.Any('normal', 'low', 'high')

        window = vs.All(int, vs.Range(min=0))
        window_floor = vs.All(int, vs.Range(min=1))
        window_ceiling = vs.Any(None, vs.All(int, vs.Range(min=1)))
        window_type = vs.Any('linear', 'exponential')
        window_factor = vs.All(int, vs.Range(min=1))

        pipeline = {vs.Required('name'): str,
                    vs.Required('manager'): manager,
                    'allow-other-connections': bool,
                    'precedence': precedence,
                    'supercedes': to_list(str),
                    'description': str,
                    'success-message': str,
                    'failure-message': str,
                    'start-message': str,
                    'merge-conflict-message': str,
                    'enqueue-message': str,
                    'no-jobs-message': str,
                    'footer-message': str,
                    'dequeue-message': str,
                    'dequeue-on-new-patchset': bool,
                    'ignore-dependencies': bool,
                    'post-review': bool,
                    'disable-after-consecutive-failures':
                        vs.All(int, vs.Range(min=1)),
                    'window': window,
                    'window-floor': window_floor,
                    'window-ceiling': window_ceiling,
                    'window-increase-type': window_type,
                    'window-increase-factor': window_factor,
                    'window-decrease-type': window_type,
                    'window-decrease-factor': window_factor,
                    '_source_context': model.SourceContext,
                    '_start_mark': model.ZuulMark,
                    }
        pipeline['require'] = self.getDriverSchema('require')
        pipeline['reject'] = self.getDriverSchema('reject')
        pipeline['trigger'] = vs.Required(self.getDriverSchema('trigger'))
        for action in ['enqueue', 'start', 'success', 'failure',
                       'merge-conflict', 'no-jobs', 'disabled',
                       'dequeue', 'config-error']:
            pipeline[action] = self.getDriverSchema('reporter')
        return vs.Schema(pipeline)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        pipeline = model.Pipeline(conf['name'], self.pcontext.tenant)
        pipeline.source_context = conf['_source_context']
        pipeline.start_mark = conf['_start_mark']
        pipeline.allow_other_connections = conf.get(
            'allow-other-connections', True)
        pipeline.description = conf.get('description')
        pipeline.supercedes = as_list(conf.get('supercedes', []))

        precedence = model.PRECEDENCE_MAP[conf.get('precedence')]
        pipeline.precedence = precedence
        pipeline.failure_message = conf.get('failure-message',
                                            "Build failed.")
        pipeline.merge_conflict_message = conf.get(
            'merge-conflict-message', "Merge Failed.\n\nThis change or one "
            "of its cross-repo dependencies was unable to be "
            "automatically merged with the current state of its "
            "repository. Please rebase the change and upload a new "
            "patchset.")

        pipeline.success_message = conf.get('success-message',
                                            "Build succeeded.")
        pipeline.footer_message = conf.get('footer-message', "")
        pipeline.start_message = conf.get('start-message',
                                          "Starting {pipeline.name} jobs.")
        pipeline.enqueue_message = conf.get('enqueue-message', "")
        pipeline.no_jobs_message = conf.get('no-jobs-message', "")
        pipeline.dequeue_message = conf.get(
            "dequeue-message", "Build canceled."
        )
        pipeline.dequeue_on_new_patchset = conf.get(
            'dequeue-on-new-patchset', True)
        pipeline.ignore_dependencies = conf.get(
            'ignore-dependencies', False)
        pipeline.post_review = conf.get(
            'post-review', False)

        # TODO: Remove in Zuul v6.0
        # Make a copy to manipulate for backwards compat.
        conf_copy = conf.copy()

        seen_connections = set()
        for conf_key, action in self.reporter_actions.items():
            reporter_set = []
            allowed_reporters = self.pcontext.tenant.allowed_reporters
            if conf_copy.get(conf_key):
                for reporter_name, params \
                    in conf_copy.get(conf_key).items():
                    if allowed_reporters is not None and \
                       reporter_name not in allowed_reporters:
                        raise UnknownConnection(reporter_name)
                    reporter = self.pcontext.connections.getReporter(
                        reporter_name, pipeline, params)
                    reporter.setAction(conf_key)
                    reporter_set.append(reporter)
                    seen_connections.add(reporter_name)
            setattr(pipeline, action, reporter_set)

        # If merge-conflict actions aren't explicit, use the failure actions
        if not pipeline.merge_conflict_actions:
            pipeline.merge_conflict_actions = pipeline.failure_actions

        # If config-error actions aren't explicit, use the failure actions
        if not pipeline.config_error_actions:
            pipeline.config_error_actions = pipeline.failure_actions

        pipeline.disable_at = conf.get(
            'disable-after-consecutive-failures', None)

        pipeline.window = conf.get('window', 20)
        pipeline.window_floor = conf.get('window-floor', 3)
        pipeline.window_ceiling = conf.get('window-ceiling', None)
        if (pipeline.window_ceiling is None):
            pipeline.window_ceiling = math.inf
        if pipeline.window_ceiling < pipeline.window_floor:
            raise Exception("Pipeline window-ceiling may not be "
                            "less than window-floor")
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
                self.pcontext.scheduler, pipeline)
        elif manager_name == 'independent':
            manager = zuul.manager.independent.IndependentPipelineManager(
                self.pcontext.scheduler, pipeline)
        elif manager_name == 'serial':
            manager = zuul.manager.serial.SerialPipelineManager(
                self.pcontext.scheduler, pipeline)
        elif manager_name == 'supercedent':
            manager = zuul.manager.supercedent.SupercedentPipelineManager(
                self.pcontext.scheduler, pipeline)

        pipeline.setManager(manager)

        with self.pcontext.errorContext(stanza='pipeline', conf=conf):
            with self.pcontext.confAttr(conf, 'require', {}) as require_dict:
                for source_name, require_config in require_dict.items():
                    source = self.pcontext.connections.getSource(source_name)
                    manager.ref_filters.extend(
                        source.getRequireFilters(
                            require_config, self.pcontext))
                    seen_connections.add(source_name)

            with self.pcontext.confAttr(conf, 'reject', {}) as reject_dict:
                for source_name, reject_config in reject_dict.items():
                    source = self.pcontext.connections.getSource(source_name)
                    manager.ref_filters.extend(
                        source.getRejectFilters(reject_config, self.pcontext))
                    seen_connections.add(source_name)

            with self.pcontext.confAttr(conf, 'trigger', {}) as trigger_dict:
                for connection_name, trigger_config in trigger_dict.items():
                    if (self.pcontext.tenant.allowed_triggers is not None and
                        (connection_name not in
                         self.pcontext.tenant.allowed_triggers)):
                        raise UnknownConnection(connection_name)
                    trigger = self.pcontext.connections.getTrigger(
                        connection_name, trigger_config)
                    pipeline.triggers.append(trigger)
                    manager.event_filters.extend(
                        trigger.getEventFilters(
                            connection_name,
                            conf['trigger'][connection_name],
                            self.pcontext))
                    seen_connections.add(connection_name)

        pipeline.connections = list(seen_connections)
        # Pipelines don't get frozen
        return pipeline


class SemaphoreParser(object):
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.SemaphoreParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()

    def getSchema(self):
        semaphore = {vs.Required('name'): str,
                     'max': int,
                     '_source_context': model.SourceContext,
                     '_start_mark': model.ZuulMark,
                     }

        return vs.Schema(semaphore)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        semaphore = model.Semaphore(conf['name'], conf.get('max', 1))
        semaphore.source_context = conf.get('_source_context')
        semaphore.start_mark = conf.get('_start_mark')
        semaphore.freeze()
        return semaphore


class QueueParser:
    def __init__(self, pcontext):
        self.log = logging.getLogger("zuul.QueueParser")
        self.pcontext = pcontext
        self.schema = self.getSchema()

    def getSchema(self):
        queue = {vs.Required('name'): str,
                 'per-branch': bool,
                 'allow-circular-dependencies': bool,
                 'dependencies-by-topic': bool,
                 '_source_context': model.SourceContext,
                 '_start_mark': model.ZuulMark,
                 }
        return vs.Schema(queue)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        queue = model.Queue(
            conf['name'],
            conf.get('per-branch', False),
            conf.get('allow-circular-dependencies', False),
            conf.get('dependencies-by-topic', False),
        )
        if (queue.dependencies_by_topic and not
            queue.allow_circular_dependencies):
            raise Exception("The 'allow-circular-dependencies' setting must be"
                            "enabled in order to use dependencies-by-topic")
        queue.source_context = conf.get('_source_context')
        queue.start_mark = conf.get('_start_mark')
        queue.freeze()
        return queue


class AuthorizationRuleParser(object):
    def __init__(self):
        self.log = logging.getLogger("zuul.AuthorizationRuleParser")
        self.schema = self.getSchema()

    def getSchema(self):
        authRule = {vs.Required('name'): str,
                    vs.Required('conditions'): to_list(dict)
                   }
        return vs.Schema(authRule)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        a = model.AuthZRuleTree(conf['name'])

        def parse_tree(node):
            if isinstance(node, list):
                return model.OrRule(parse_tree(x) for x in node)
            elif isinstance(node, dict):
                subrules = []
                for claim, value in node.items():
                    if claim == 'zuul_uid':
                        claim = '__zuul_uid_claim'
                    subrules.append(model.ClaimRule(claim, value))
                return model.AndRule(subrules)
            else:
                raise Exception('Invalid claim declaration %r' % node)

        a.ruletree = parse_tree(conf['conditions'])
        return a


class GlobalSemaphoreParser(object):
    def __init__(self):
        self.log = logging.getLogger("zuul.GlobalSemaphoreParser")
        self.schema = self.getSchema()

    def getSchema(self):
        semaphore = {vs.Required('name'): str,
                     'max': int,
                     }

        return vs.Schema(semaphore)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        semaphore = model.Semaphore(conf['name'], conf.get('max', 1),
                                    global_scope=True)
        semaphore.freeze()
        return semaphore


class ApiRootParser(object):
    def __init__(self):
        self.log = logging.getLogger("zuul.ApiRootParser")
        self.schema = self.getSchema()

    def getSchema(self):
        api_root = {
            'authentication-realm': str,
            'access-rules': to_list(str),
        }
        return vs.Schema(api_root)

    def fromYaml(self, conf):
        conf = copy_safe_config(conf)
        self.schema(conf)
        api_root = model.ApiRoot(conf.get('authentication-realm'))
        api_root.access_rules = conf.get('access-rules', [])
        api_root.freeze()
        return api_root


class ParseContext(object):
    """Hold information about a particular run of the parser"""

    def __init__(self, connections, scheduler, tenant, ansible_manager):
        self.loading_errors = model.LoadingErrors()
        self.connections = connections
        self.scheduler = scheduler
        self.tenant = tenant
        self.ansible_manager = ansible_manager
        self.pragma_parser = PragmaParser(self)
        self.pipeline_parser = PipelineParser(self)
        self.nodeset_parser = NodeSetParser(self)
        self.secret_parser = SecretParser(self)
        self.job_parser = JobParser(self)
        self.semaphore_parser = SemaphoreParser(self)
        self.queue_parser = QueueParser(self)
        self.project_template_parser = ProjectTemplateParser(self)
        self.project_parser = ProjectParser(self)
        acc = LocalAccumulator(self.loading_errors)
        # Currently we use thread local storage to ensure that we
        # don't accidentally use the error context stack from one of
        # our threadpool workers.  In the future, we may be able to
        # refactor so that the workers branch it whenever they start
        # work.
        self._thread_local = threading.local()
        self._thread_local.accumulators = [acc]

    @property
    def accumulator(self):
        return self._thread_local.accumulators[-1]

    @contextmanager
    def errorContext(self, source_context=None, stanza=None,
                     conf=None, attr=None):
        acc = self.accumulator.extend(source_context=source_context,
                                      stanza=stanza,
                                      conf=conf,
                                      attr=attr)
        self._thread_local.accumulators.append(acc)
        try:
            yield
        finally:
            if len(self._thread_local.accumulators) > 1:
                self._thread_local.accumulators.pop()

    @contextmanager
    def confAttr(self, conf, attr, default=None):
        found = None
        for k in conf.keys():
            if k == attr:
                found = k
                break
        if found is not None:
            with self.errorContext(attr=found):
                yield conf[found]
        else:
            yield default

    def getImpliedBranches(self, source_context):
        # If the user has set a pragma directive for this, use the
        # value (ixf unset, the value is None).
        if source_context.implied_branch_matchers is True:
            if source_context.implied_branches is not None:
                return source_context.implied_branches
            return [change_matcher.ImpliedBranchMatcher(
                ZuulRegex(source_context.branch))]
        elif source_context.implied_branch_matchers is False:
            return None

        # If this is a trusted project, don't create implied branch
        # matchers.
        if source_context.trusted:
            return None

        # If this project only has one branch, don't create implied
        # branch matchers.  This way central job repos can work.
        branches = self.tenant.getProjectBranches(
            source_context.project_canonical_name)
        if len(branches) == 1:
            return None

        if source_context.implied_branches is not None:
            return source_context.implied_branches
        return [change_matcher.ImpliedBranchMatcher(
            ZuulRegex(source_context.branch))]


class TenantParser(object):
    def __init__(self, connections, zk_client, scheduler, merger, keystorage,
                 zuul_globals, statsd, unparsed_config_cache):
        self.log = logging.getLogger("zuul.TenantParser")
        self.connections = connections
        self.zk_client = zk_client
        self.scheduler = scheduler
        self.merger = merger
        self.keystorage = keystorage
        self.globals = zuul_globals
        self.statsd = statsd
        self.unparsed_config_cache = unparsed_config_cache

    classes = vs.Any('pipeline', 'job', 'semaphore', 'project',
                     'project-template', 'nodeset', 'secret', 'queue')

    project_dict = {str: {
        'include': to_list(classes),
        'exclude': to_list(classes),
        'shadow': to_list(str),
        'exclude-unprotected-branches': bool,
        'exclude-locked-branches': bool,
        'extra-config-paths': no_dup_config_paths,
        'load-branch': str,
        'include-branches': to_list(str),
        'exclude-branches': to_list(str),
        'always-dynamic-branches': to_list(str),
        'allow-circular-dependencies': bool,
        'implied-branch-matchers': bool,
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

    def validateTenantSources(self):
        def v(value, path=[]):
            if isinstance(value, dict):
                for k, val in value.items():
                    self.connections.getSource(k)
                    self.validateTenantSource(val, path + [k])
            else:
                raise vs.Invalid("Invalid tenant source", path)
        return v

    def validateTenantSource(self, value, path=[]):
        self.tenant_source(value)

    def getSchema(self):
        tenant = {vs.Required('name'): str,
                  'max-dependencies': int,
                  'max-nodes-per-job': int,
                  'max-job-timeout': int,
                  'source': self.validateTenantSources(),
                  'exclude-unprotected-branches': bool,
                  'exclude-locked-branches': bool,
                  'allowed-triggers': to_list(str),
                  'allowed-reporters': to_list(str),
                  'allowed-labels': to_list(str),
                  'disallowed-labels': to_list(str),
                  'allow-circular-dependencies': bool,
                  'default-parent': str,
                  'default-ansible-version': vs.Any(str, float, int),
                  'access-rules': to_list(str),
                  'admin-rules': to_list(str),
                  'semaphores': to_list(str),
                  'authentication-realm': str,
                  # TODO: Ignored, allowed for backwards compat, remove for v5.
                  'report-build-page': bool,
                  'web-root': str,
                  }
        return vs.Schema(tenant)

    def fromYaml(self, abide, conf, ansible_manager, executor, min_ltimes=None,
                 layout_uuid=None, branch_cache_min_ltimes=None,
                 ignore_cat_exception=True):
        # Note: This vs schema validation is not necessary in most cases as we
        # verify the schema when loading tenant configs into zookeeper.
        # However, it is theoretically possible in a multi scheduler setup that
        # one scheduler would load the config into zk with validated schema
        # then another newer or older scheduler could load it from zk and fail.
        # We validate again to help users debug this situation should it
        # happen.
        self.getSchema()(conf)
        tenant = model.Tenant(conf['name'])
        pcontext = ParseContext(self.connections, self.scheduler,
                                tenant, ansible_manager)
        if conf.get('max-dependencies') is not None:
            tenant.max_dependencies = conf['max-dependencies']
        if conf.get('max-nodes-per-job') is not None:
            tenant.max_nodes_per_job = conf['max-nodes-per-job']
        if conf.get('max-job-timeout') is not None:
            tenant.max_job_timeout = int(conf['max-job-timeout'])
        if conf.get('exclude-unprotected-branches') is not None:
            tenant.exclude_unprotected_branches = \
                conf['exclude-unprotected-branches']
        if conf.get('exclude-locked-branches') is not None:
            tenant.exclude_locked_branches = \
                conf['exclude-locked-branches']
        if conf.get('admin-rules') is not None:
            tenant.admin_rules = as_list(conf['admin-rules'])
        if conf.get('access-rules') is not None:
            tenant.access_rules = as_list(conf['access-rules'])
        if conf.get('authentication-realm') is not None:
            tenant.default_auth_realm = conf['authentication-realm']
        if conf.get('semaphores') is not None:
            tenant.global_semaphores = set(as_list(conf['semaphores']))
            for semaphore_name in tenant.global_semaphores:
                if semaphore_name not in abide.semaphores:
                    raise GlobalSemaphoreNotFoundError(semaphore_name)
        tenant.web_root = conf.get('web-root', self.globals.web_root)
        if tenant.web_root and not tenant.web_root.endswith('/'):
            tenant.web_root += '/'
        tenant.allowed_triggers = conf.get('allowed-triggers')
        tenant.allowed_reporters = conf.get('allowed-reporters')
        tenant.allowed_labels = conf.get('allowed-labels')
        tenant.disallowed_labels = conf.get('disallowed-labels')
        tenant.default_base_job = conf.get('default-parent', 'base')

        tenant.unparsed_config = conf
        # tpcs is TenantProjectConfigs
        tpc_registry = abide.getTPCRegistry(tenant.name)
        config_tpcs = tpc_registry.getConfigTPCs()
        for tpc in config_tpcs:
            tenant.addConfigProject(tpc)
        untrusted_tpcs = tpc_registry.getUntrustedTPCs()
        for tpc in untrusted_tpcs:
            tenant.addUntrustedProject(tpc)

        # Get branches in parallel
        branch_futures = {}
        for tpc in config_tpcs + untrusted_tpcs:
            future = executor.submit(self._getProjectBranches,
                                     tenant, tpc, branch_cache_min_ltimes)
            branch_futures[future] = tpc

        for branch_future in as_completed(branch_futures.keys()):
            tpc = branch_futures[branch_future]
            trusted, _ = tenant.getProject(tpc.project.canonical_name)
            source_context = model.SourceContext(
                tpc.project.canonical_name, tpc.project.name,
                tpc.project.connection_name, None, None, trusted)
            with pcontext.errorContext(source_context=source_context):
                with pcontext.accumulator.catchErrors():
                    self._getProjectBranches(tenant, tpc,
                                             branch_cache_min_ltimes)
                    self._resolveShadowProjects(tenant, tpc)

        # Set default ansible version
        default_ansible_version = conf.get('default-ansible-version')
        if default_ansible_version is not None:
            # The ansible version can be interpreted as float or int
            # by yaml so make sure it's a string.
            default_ansible_version = str(default_ansible_version)
            ansible_manager.requestVersion(default_ansible_version)
        else:
            default_ansible_version = ansible_manager.default_version
        tenant.default_ansible_version = default_ansible_version

        # Start by fetching any YAML needed by this tenant which isn't
        # already cached.  Full reconfigurations start with an empty
        # cache.
        self._cacheTenantYAML(abide, tenant, pcontext,
                              min_ltimes, executor, ignore_cat_exception)

        # Then collect the appropriate YAML based on this tenant
        # config.
        config_projects_config, untrusted_projects_config = \
            self._loadTenantYAML(abide, tenant, pcontext)

        # Then convert the YAML to configuration objects which we
        # cache on the tenant.
        tenant.config_projects_config = self.parseConfig(
            tenant, config_projects_config, pcontext)
        tenant.untrusted_projects_config = self.parseConfig(
            tenant, untrusted_projects_config, pcontext)

        # Combine the trusted and untrusted config objects
        parsed_config = model.ParsedConfig()
        parsed_config.extend(tenant.config_projects_config)
        parsed_config.extend(tenant.untrusted_projects_config)

        # Cache all of the objects on the individual project-branches
        # for later use during dynamic reconfigurations.
        self.cacheConfig(tenant, parsed_config)

        tenant.layout = self._parseLayout(
            tenant, parsed_config, pcontext, layout_uuid)

        tenant.semaphore_handler = SemaphoreHandler(
            self.zk_client, self.statsd, tenant.name, tenant.layout, abide,
            read_only=(not bool(self.scheduler))
        )
        if self.scheduler:
            # Only call the postConfig hook if we have a scheduler as this will
            # change data in ZooKeeper. In case we are in a zuul-web context,
            # we don't want to do that.
            for pipeline in tenant.layout.pipelines.values():
                pipeline.manager._postConfig()

        return tenant

    def _resolveShadowProjects(self, tenant, tpc):
        shadow_projects = []
        for sp in tpc.shadow_projects:
            _, project = tenant.getProject(sp)
            if project is None:
                raise ProjectNotFoundError(sp)
            shadow_projects.append(project.canonical_name)
        tpc.shadow_projects = frozenset(shadow_projects)

    def _getProjectBranches(self, tenant, tpc, branch_cache_min_ltimes=None):
        if branch_cache_min_ltimes is not None:
            # Use try/except here instead of .get in order to allow
            # defaultdict to supply a default other than our default
            # of -1.
            try:
                min_ltime = branch_cache_min_ltimes[
                    tpc.project.source.connection.connection_name]
            except KeyError:
                min_ltime = -1
        else:
            min_ltime = -1
        branches = sorted(tpc.project.source.getProjectBranches(
            tpc.project, tenant, min_ltime))
        default_branch = tpc.project.source.getProjectDefaultBranch(
            tpc.project, tenant, min_ltime)
        if default_branch in branches:
            branches.remove(default_branch)
            branches = [default_branch] + branches
        static_branches = []
        always_dynamic_branches = []
        for b in branches:
            if tpc.includesBranch(b):
                static_branches.append(b)
            elif tpc.isAlwaysDynamicBranch(b):
                always_dynamic_branches.append(b)
        tpc.branches = static_branches
        tpc.dynamic_branches = always_dynamic_branches

        tpc.merge_modes = tpc.project.source.getProjectMergeModes(
            tpc.project, tenant, min_ltime)

    def _loadProjectKeys(self, connection_name, project):
        project.private_secrets_key, project.public_secrets_key = (
            self.keystorage.getProjectSecretsKeys(
                connection_name, project.name
            )
        )

        project.private_ssh_key, project.public_ssh_key = (
            self.keystorage.getProjectSSHKeys(connection_name, project.name)
        )

    @staticmethod
    def _getProject(source, conf, current_include):
        extra_config_files = ()
        extra_config_dirs = ()

        if isinstance(conf, str):
            # Return a project object whether conf is a dict or a str
            project = source.getProject(conf)
            project_include = current_include
            shadow_projects = []
            project_exclude_unprotected_branches = None
            project_exclude_locked_branches = None
            project_include_branches = None
            project_exclude_branches = None
            project_always_dynamic_branches = None
            project_load_branch = None
            project_implied_branch_matchers = None
        else:
            project_name = list(conf.keys())[0]
            project = source.getProject(project_name)
            shadow_projects = as_list(conf[project_name].get('shadow', []))

            # We check for None since the user may set include to an empty list
            if conf[project_name].get("include") is None:
                project_include = current_include
            else:
                project_include = frozenset(
                    as_list(conf[project_name]['include']))
            project_exclude = frozenset(
                as_list(conf[project_name].get('exclude', [])))
            if project_exclude:
                project_include = frozenset(project_include - project_exclude)
            project_exclude_unprotected_branches = conf[project_name].get(
                'exclude-unprotected-branches', None)
            project_exclude_locked_branches = conf[project_name].get(
                'exclude-locked-branches', None)
            project_include_branches = conf[project_name].get(
                'include-branches', None)
            if project_include_branches is not None:
                project_include_branches = [
                    re.compile(b) for b in as_list(project_include_branches)
                ]
            exclude_branches = conf[project_name].get(
                'exclude-branches', None)
            if exclude_branches is not None:
                project_exclude_branches = [
                    re.compile(b) for b in as_list(exclude_branches)
                ]
            else:
                project_exclude_branches = None
            always_dynamic_branches = conf[project_name].get(
                'always-dynamic-branches', None)
            if always_dynamic_branches is not None:
                if project_exclude_branches is None:
                    project_exclude_branches = []
                    exclude_branches = []
                project_always_dynamic_branches = []
                for b in always_dynamic_branches:
                    rb = re.compile(b)
                    if b not in exclude_branches:
                        project_exclude_branches.append(rb)
                    project_always_dynamic_branches.append(rb)
            else:
                project_always_dynamic_branches = None
            if conf[project_name].get('extra-config-paths') is not None:
                extra_config_paths = as_list(
                    conf[project_name]['extra-config-paths'])
                extra_config_files = tuple([x for x in extra_config_paths
                                            if not x.endswith('/')])
                extra_config_dirs = tuple([x[:-1] for x in extra_config_paths
                                           if x.endswith('/')])
            project_load_branch = conf[project_name].get(
                'load-branch', None)
            project_implied_branch_matchers = conf[project_name].get(
                'implied-branch-matchers', None)

        tenant_project_config = model.TenantProjectConfig(project)
        tenant_project_config.load_classes = frozenset(project_include)
        tenant_project_config.shadow_projects = shadow_projects
        tenant_project_config.exclude_unprotected_branches = \
            project_exclude_unprotected_branches
        tenant_project_config.exclude_locked_branches = \
            project_exclude_locked_branches
        tenant_project_config.include_branches = project_include_branches
        tenant_project_config.exclude_branches = project_exclude_branches
        tenant_project_config.always_dynamic_branches = \
            project_always_dynamic_branches
        tenant_project_config.extra_config_files = extra_config_files
        tenant_project_config.extra_config_dirs = extra_config_dirs
        tenant_project_config.load_branch = project_load_branch
        tenant_project_config.implied_branch_matchers = \
            project_implied_branch_matchers

        return tenant_project_config

    def _getProjects(self, source, conf, current_include):
        # Return a project object whether conf is a dict or a str
        projects = []
        if isinstance(conf, str):
            # A simple project name string
            projects.append(self._getProject(source, conf, current_include))
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
                sub_projects = self._getProjects(
                    source, project, current_include)
                projects.extend(sub_projects)
        elif len(conf.keys()) == 1:
            # A project with overrides
            projects.append(self._getProject(
                source, conf, current_include))
        else:
            raise Exception("Unable to parse project %s", conf)
        return projects

    def loadTenantProjects(self, conf_tenant, executor):
        config_projects = []
        untrusted_projects = []

        default_include = frozenset(['pipeline', 'job', 'semaphore', 'project',
                                     'secret', 'project-template', 'nodeset',
                                     'queue'])

        futures = []
        for source_name, conf_source in conf_tenant.get('source', {}).items():
            source = self.connections.getSource(source_name)

            current_include = default_include
            for conf_repo in conf_source.get('config-projects', []):
                # tpcs = TenantProjectConfigs
                tpcs = self._getProjects(source, conf_repo, current_include)
                for tpc in tpcs:
                    futures.append(executor.submit(
                        self._loadProjectKeys, source_name, tpc.project))
                    config_projects.append(tpc)

            current_include = frozenset(default_include - set(['pipeline']))
            for conf_repo in conf_source.get('untrusted-projects', []):
                tpcs = self._getProjects(source, conf_repo,
                                         current_include)
                for tpc in tpcs:
                    futures.append(executor.submit(
                        self._loadProjectKeys, source_name, tpc.project))
                    untrusted_projects.append(tpc)

        for f in futures:
            f.result()
        return config_projects, untrusted_projects

    def _cacheTenantYAML(self, abide, tenant, parse_context, min_ltimes,
                         executor, ignore_cat_exception=True):
        # min_ltimes can be the following: None (that means that we
        # should not use the file cache at all) or a nested dict of
        # project and branch to ltime.  A value of None usually means
        # we are being called from the command line config validator.
        # However, if the model api is old, we may be operating in
        # compatibility mode and are loading a layout without a stored
        # min_ltimes.  In that case, we treat it as if min_ltimes is a
        # defaultdict of -1.

        # If min_ltimes is not None, then it is mutated and returned
        # with the actual ltimes of each entry in the unparsed branch
        # cache.

        if min_ltimes is None and COMPONENT_REGISTRY.model_api < 6:
            min_ltimes = collections.defaultdict(
                lambda: collections.defaultdict(lambda: -1))

        # If the ltime is -1, then we should consider the file cache
        # valid.  If we have an unparsed branch cache entry for the
        # project-branch, we should use it, otherwise we should update
        # our unparsed branch cache from whatever is in the file
        # cache.

        # If the ltime is otherwise, then if our unparsed branch cache
        # is valid for that ltime, we should use the contents.
        # Otherwise if the files cache is valid for the ltime, we
        # should update our unparsed branch cache from the files cache
        # and use that.  Otherwise, we should run a cat job to update
        # the files cache, then update our unparsed branch cache from
        # that.

        # The circumstances under which this method is called are:

        # Prime:
        #   min_ltimes is None: backwards compat from old model api
        #   which we treat as a universal ltime of -1.
        #   We'll either get an actual min_ltimes dict from the last
        #   reconfig, or -1 if this is a new tenant.
        #   In all cases, our unparsed branch cache will be empty, so
        #   we will always either load data from zk or issue a cat job
        #   as appropriate.

        # Background layout update:
        #   min_ltimes is None: backwards compat from old model api
        #   which we treat as a universal ltime of -1.
        #   Otherwise, min_ltimes will always be the actual min_ltimes
        #   from the last reconfig.  No cat jobs should be needed; we
        #   either have an unparsed branch cache valid for the ltime,
        #   or we update it from ZK which should be valid.

        # Smart or full reconfigure:
        #   min_ltime is -1: a smart reconfig: consider the caches valid
        #   min_ltime is the event time: a full reconfig; we update
        #   both of the ccahes as necessary.

        # Tenant reconfigure:
        #   min_ltime is -1: this project-branch is unchanged by the
        #   tenant reconfig event, so consider the caches valid.
        #   min_ltime is the event time: this project-branch was updated
        #   so check the caches.

        jobs = []

        futures = []
        for project in itertools.chain(
                tenant.config_projects, tenant.untrusted_projects):
            tpc = tenant.project_configs[project.canonical_name]
            # For each branch in the repo, get the zuul.yaml for that
            # branch.  Remember the branch and then implicitly add a
            # branch selector to each job there.  This makes the
            # in-repo configuration apply only to that branch.
            branches = tenant.getProjectBranches(project.canonical_name)
            for branch in branches:
                if not tpc.load_classes:
                    # If all config classes are excluded then do not
                    # request any getFiles jobs.
                    continue
                futures.append(executor.submit(self._cacheTenantYAMLBranch,
                                               abide, tenant,
                                               parse_context.accumulator,
                                               min_ltimes, tpc, project,
                                               branch, jobs))
        for future in futures:
            future.result()

        for i, job in enumerate(jobs, start=1):
            try:
                try:
                    self._processCatJob(abide, tenant, parse_context, job,
                                        min_ltimes)
                except TimeoutError:
                    self.merger.cancel(job)
                    raise
            except Exception:
                self.log.exception("Error processing cat job")
                if not ignore_cat_exception:
                    # Cancel remaining jobs
                    for cancel_job in jobs[i:]:
                        self.log.debug("Canceling cat job %s", cancel_job)
                        try:
                            self.merger.cancel(cancel_job)
                        except Exception:
                            self.log.exception(
                                "Unable to cancel job %s", cancel_job)
                    raise

    def _cacheTenantYAMLBranch(self, abide, tenant, error_accumulator,
                               min_ltimes, tpc, project, branch, jobs):
        # This is the middle section of _cacheTenantYAML, called for
        # each project-branch.  It's a separate method so we can
        # execute it in parallel.  The "jobs" argument is mutated and
        # accumulates a list of all merger jobs submitted.
        source_context = model.SourceContext(
            project.canonical_name, project.name,
            project.connection_name, branch, '', False,
            tpc.implied_branch_matchers)
        # We keep a local accumulator here because we're in a
        # threadpool so we can't use the parse context stack.
        error_accumulator = error_accumulator.extend(source_context)
        if min_ltimes is not None:
            files_cache = self.unparsed_config_cache.getFilesCache(
                project.canonical_name, branch)
            branch_cache = abide.getUnparsedBranchCache(
                project.canonical_name, branch)
            try:
                pb_ltime = min_ltimes[project.canonical_name][branch]
                # If our unparsed branch cache is valid for the
                # time, then we don't need to do anything else.
                bc_ltime = branch_cache.getValidFor(tpc, ZUUL_CONF_ROOT,
                                                    pb_ltime)
                if bc_ltime is not None:
                    min_ltimes[project.canonical_name][branch] = bc_ltime
                    return
            except KeyError:
                self.log.exception(
                    "Min. ltime missing for project/branch")
                pb_ltime = -1

            with self.unparsed_config_cache.readLock(
                    project.canonical_name):
                if files_cache.isValidFor(tpc, pb_ltime):
                    self.log.debug(
                        "Using files from cache for project "
                        "%s @%s: %s",
                        project.canonical_name, branch,
                        list(files_cache.keys()))
                    self._updateUnparsedBranchCache(
                        abide, tenant, source_context, files_cache,
                        error_accumulator, files_cache.ltime,
                        min_ltimes)
                    return

        extra_config_files = abide.getExtraConfigFiles(project.name)
        extra_config_dirs = abide.getExtraConfigDirs(project.name)
        if not self.merger:
            err = Exception(
                "Configuration files missing from cache. "
                "Check Zuul scheduler logs for more information.")
            error_accumulator.addError(err)
            return
        ltime = self.zk_client.getCurrentLtime()
        job = self.merger.getFiles(
            project.source.connection.connection_name,
            project.name, branch,
            files=(['zuul.yaml', '.zuul.yaml'] +
                   list(extra_config_files)),
            dirs=['zuul.d', '.zuul.d'] + list(extra_config_dirs))
        self.log.debug("Submitting cat job %s for %s %s %s" % (
            job, project.source.connection.connection_name,
            project.name, branch))
        job.extra_config_files = extra_config_files
        job.extra_config_dirs = extra_config_dirs
        job.ltime = ltime
        job.source_context = source_context
        jobs.append(job)

    def _processCatJob(self, abide, tenant, parse_context, job, min_ltimes):
        # Called at the end of _cacheTenantYAML after all cat jobs
        # have been submitted
        self.log.debug("Waiting for cat job %s" % (job,))
        res = job.wait(self.merger.git_timeout)
        if not res:
            # We timed out
            raise TimeoutError(f"Cat job {job} timed out; consider setting "
                               "merger.git_timeout in zuul.conf")
        if not job.updated:
            raise Exception("Cat job %s failed" % (job,))
        self.log.debug("Cat job %s got files %s" %
                       (job, job.files.keys()))

        with parse_context.errorContext(source_context=job.source_context):
            self._updateUnparsedBranchCache(
                abide, tenant, job.source_context,
                job.files, parse_context.accumulator,
                job.ltime, min_ltimes)

        # Save all config files in Zookeeper (not just for the current tpc)
        files_cache = self.unparsed_config_cache.getFilesCache(
            job.source_context.project_canonical_name,
            job.source_context.branch)
        with self.unparsed_config_cache.writeLock(
                job.source_context.project_canonical_name):
            # Prevent files cache ltime from going backward
            if files_cache.ltime >= job.ltime:
                self.log.info(
                    "Discarding job %s result since the files cache was "
                    "updated in the meantime", job)
                return
            # Since the cat job returns all required config files
            # for ALL tenants the project is a part of, we can
            # clear the whole cache and then populate it with the
            # updated content.
            files_cache.clear()
            for fn, content in job.files.items():
                # Cache file in Zookeeper
                if content is not None:
                    files_cache[fn] = content
            files_cache.setValidFor(job.extra_config_files,
                                    job.extra_config_dirs,
                                    job.ltime)

    def _updateUnparsedBranchCache(self, abide, tenant, source_context, files,
                                   error_accumulator, ltime, min_ltimes):
        loaded = False
        tpc = tenant.project_configs[source_context.project_canonical_name]
        branch_cache = abide.getUnparsedBranchCache(
            source_context.project_canonical_name,
            source_context.branch)
        valid_dirs = ("zuul.d", ".zuul.d") + tpc.extra_config_dirs
        for conf_root in (ZUUL_CONF_ROOT + tpc.extra_config_files
                          + tpc.extra_config_dirs):
            for fn in sorted(files.keys()):
                if not (fn == conf_root
                        or (conf_root in valid_dirs
                            and fn.startswith(f"{conf_root}/"))):
                    continue
                if not (file_data := files.get(fn)):
                    continue
                # Warn if there is more than one configuration in a
                # project-branch (unless an "extra" file/dir).  We
                # continue to add the data to the cache for use by
                # other tenants, but we will filter it out when we
                # retrieve it later.
                fn_root = fn.split('/')[0]
                if (fn_root in ZUUL_CONF_ROOT):
                    if (loaded and loaded != conf_root):
                        err = MultipleProjectConfigurations(source_context)
                        error_accumulator.addError(err)
                    loaded = conf_root
                # Create a new source_context so we have unique filenames.
                source_context = source_context.copy()
                source_context.path = fn
                self.log.info(
                    "Loading configuration from %s" %
                    (source_context,))
                # Make a new error accumulator; we may be in a threadpool
                # so we can't use the stack.
                local_accumulator = error_accumulator.extend(
                    source_context=source_context)
                incdata = self.loadProjectYAML(
                    file_data, source_context, local_accumulator)
                branch_cache.put(source_context.path, incdata, ltime)
        branch_cache.setValidFor(tpc, ZUUL_CONF_ROOT, ltime)
        if min_ltimes is not None:
            min_ltimes[source_context.project_canonical_name][
                source_context.branch] = ltime

    def _loadTenantYAML(self, abide, tenant, parse_context):
        config_projects_config = model.UnparsedConfig()
        untrusted_projects_config = model.UnparsedConfig()

        for project in tenant.config_projects:
            tpc = tenant.project_configs.get(project.canonical_name)
            branch = tpc.load_branch if tpc.load_branch else 'master'
            branch_cache = abide.getUnparsedBranchCache(
                project.canonical_name, branch)
            tpc = tenant.project_configs[project.canonical_name]
            unparsed_branch_config = branch_cache.get(tpc, ZUUL_CONF_ROOT)

            if unparsed_branch_config:
                unparsed_branch_config = self.filterConfigProjectYAML(
                    unparsed_branch_config)

                config_projects_config.extend(unparsed_branch_config)

        for project in tenant.untrusted_projects:
            branches = tenant.getProjectBranches(project.canonical_name)
            for branch in branches:
                branch_cache = abide.getUnparsedBranchCache(
                    project.canonical_name, branch)
                tpc = tenant.project_configs[project.canonical_name]
                unparsed_branch_config = branch_cache.get(tpc, ZUUL_CONF_ROOT)
                if unparsed_branch_config:
                    unparsed_branch_config = self.filterUntrustedProjectYAML(
                        unparsed_branch_config, parse_context)

                    untrusted_projects_config.extend(unparsed_branch_config)
        return config_projects_config, untrusted_projects_config

    def loadProjectYAML(self, data, source_context, error_accumulator):
        config = model.UnparsedConfig()
        with error_accumulator.catchErrors():
            r = safe_load_yaml(data, source_context)
            config.extend(r)
        return config

    def filterConfigProjectYAML(self, data):
        # Any config object may appear in a config project.
        return data.copy(trusted=True)

    def filterUntrustedProjectYAML(self, data, parse_context):
        if data and data.pipelines:
            with parse_context.errorContext(stanza='pipeline',
                                            conf=data.pipelines[0]):
                parse_context.accumulator.addError(PipelineNotPermittedError())
        return data.copy(trusted=False)

    def _getLoadClasses(self, tenant, conf_object):
        project = conf_object.get('_source_context').project_canonical_name
        tpc = tenant.project_configs[project]
        return tpc.load_classes

    def parseConfig(self, tenant, unparsed_config, pcontext):
        parsed_config = model.ParsedConfig()

        # Handle pragma items first since they modify the source context
        # used by other classes.
        for config_pragma in unparsed_config.pragmas:
            with pcontext.errorContext(stanza='pragma', conf=config_pragma):
                with pcontext.accumulator.catchErrors():
                    pcontext.pragma_parser.fromYaml(config_pragma)

        for config_pipeline in unparsed_config.pipelines:
            classes = self._getLoadClasses(tenant, config_pipeline)
            if 'pipeline' not in classes:
                continue
            with pcontext.errorContext(stanza='pipeline',
                                       conf=config_pipeline):
                with pcontext.accumulator.catchErrors():
                    parsed_config.pipelines.append(
                        pcontext.pipeline_parser.fromYaml(config_pipeline))

        for config_nodeset in unparsed_config.nodesets:
            classes = self._getLoadClasses(tenant, config_nodeset)
            if 'nodeset' not in classes:
                continue
            with pcontext.errorContext(stanza='nodeset', conf=config_nodeset):
                with pcontext.accumulator.catchErrors():
                    parsed_config.nodesets.append(
                        pcontext.nodeset_parser.fromYaml(config_nodeset))

        for config_secret in unparsed_config.secrets:
            classes = self._getLoadClasses(tenant, config_secret)
            if 'secret' not in classes:
                continue
            with pcontext.errorContext(stanza='secret', conf=config_secret):
                with pcontext.accumulator.catchErrors():
                    parsed_config.secrets.append(
                        pcontext.secret_parser.fromYaml(config_secret))

        for config_job in unparsed_config.jobs:
            classes = self._getLoadClasses(tenant, config_job)
            if 'job' not in classes:
                continue
            with pcontext.errorContext(stanza='job', conf=config_job):
                with pcontext.accumulator.catchErrors():
                    parsed_config.jobs.append(
                        pcontext.job_parser.fromYaml(config_job))

        for config_semaphore in unparsed_config.semaphores:
            classes = self._getLoadClasses(tenant, config_semaphore)
            if 'semaphore' not in classes:
                continue
            with pcontext.errorContext(stanza='semaphore',
                                       conf=config_semaphore):
                with pcontext.accumulator.catchErrors():
                    parsed_config.semaphores.append(
                        pcontext.semaphore_parser.fromYaml(config_semaphore))

        for config_queue in unparsed_config.queues:
            classes = self._getLoadClasses(tenant, config_queue)
            if 'queue' not in classes:
                continue
            with pcontext.errorContext(stanza='queue', conf=config_queue):
                with pcontext.accumulator.catchErrors():
                    parsed_config.queues.append(
                        pcontext.queue_parser.fromYaml(config_queue))

        for config_template in unparsed_config.project_templates:
            classes = self._getLoadClasses(tenant, config_template)
            if 'project-template' not in classes:
                continue
            with pcontext.errorContext(stanza='project-template',
                                       conf=config_template):
                with pcontext.accumulator.catchErrors():
                    parsed_config.project_templates.append(
                        pcontext.project_template_parser.fromYaml(
                            config_template))

        for config_project in unparsed_config.projects:
            classes = self._getLoadClasses(tenant, config_project)
            if 'project' not in classes:
                continue
            with pcontext.errorContext(stanza='project', conf=config_project):
                with pcontext.accumulator.catchErrors():
                    # we need to separate the regex projects as they are
                    # processed differently later
                    name = config_project.get('name')
                    parsed_project = pcontext.project_parser.fromYaml(
                        config_project)
                    if name and name.startswith('^'):
                        parsed_config.projects_by_regex.setdefault(
                            name, []).append(parsed_project)
                    else:
                        parsed_config.projects.append(parsed_project)

        return parsed_config

    def cacheConfig(self, tenant, parsed_config):
        def _cache(attr, obj):
            tpc = tenant.project_configs[
                obj.source_context.project_canonical_name]
            branch_cache = tpc.parsed_branch_config.get(
                obj.source_context.branch)
            if branch_cache is None:
                branch_cache = tpc.parsed_branch_config.setdefault(
                    obj.source_context.branch,
                    model.ParsedConfig())
            lst = getattr(branch_cache, attr)
            lst.append(obj)

        # We don't cache pragma objects as they are acted on when
        # parsed.

        for pipeline in parsed_config.pipelines:
            _cache('pipelines', pipeline)

        for nodeset in parsed_config.nodesets:
            _cache('nodesets', nodeset)

        for secret in parsed_config.secrets:
            _cache('secrets', secret)

        for job in parsed_config.jobs:
            _cache('jobs', job)

        for queue in parsed_config.queues:
            _cache('queues', queue)

        for semaphore in parsed_config.semaphores:
            _cache('semaphores', semaphore)

        for template in parsed_config.project_templates:
            _cache('project_templates', template)

        for project_config in parsed_config.projects:
            _cache('projects', project_config)

    def _addLayoutItems(self, layout, tenant, parsed_config,
                        parse_context, skip_pipelines=False,
                        skip_semaphores=False):
        # TODO(jeblair): make sure everything needing
        # reference_exceptions has it; add tests if needed.
        if not skip_pipelines:
            for pipeline in parsed_config.pipelines:
                with parse_context.errorContext(stanza='pipeline',
                                                conf=pipeline):
                    with parse_context.accumulator.catchErrors():
                        layout.addPipeline(pipeline)

        for nodeset in parsed_config.nodesets:
            with parse_context.errorContext(stanza='nodeset', conf=nodeset):
                with parse_context.accumulator.catchErrors():
                    layout.addNodeSet(nodeset)

        for secret in parsed_config.secrets:
            with parse_context.errorContext(stanza='secret', conf=secret):
                with parse_context.accumulator.catchErrors():
                    layout.addSecret(secret)

        for job in parsed_config.jobs:
            with parse_context.errorContext(stanza='job', conf=job):
                with parse_context.accumulator.catchErrors():
                    added = layout.addJob(job)
                    if not added:
                        self.log.debug(
                            "Skipped adding job %s which shadows "
                            "an existing job", job)

        # Now that all the jobs are loaded, verify references to other
        # config objects.
        for nodeset in layout.nodesets.values():
            with parse_context.errorContext(stanza='nodeset', conf=nodeset):
                with parse_context.accumulator.catchErrors():
                    nodeset.validateReferences(layout)
        for jobs in layout.jobs.values():
            for job in jobs:
                with parse_context.errorContext(stanza='job', conf=job):
                    with parse_context.accumulator.catchErrors():
                        job.validateReferences(layout)
        for pipeline in layout.pipelines.values():
            with parse_context.errorContext(stanza='pipeline', conf=pipeline):
                with parse_context.accumulator.catchErrors():
                    pipeline.validateReferences(layout)

        if skip_semaphores:
            # We should not actually update the layout with new
            # semaphores, but so that we can validate that the config
            # is correct, create a shadow layout here to which we add
            # new semaphores so validation is complete.
            semaphore_layout = model.Layout(tenant)
        else:
            semaphore_layout = layout
        for semaphore in parsed_config.semaphores:
            with parse_context.errorContext(stanza='semaphore',
                                            conf=semaphore):
                with parse_context.accumulator.catchErrors():
                    semaphore_layout.addSemaphore(semaphore)

        for queue in parsed_config.queues:
            with parse_context.errorContext(stanza='queue', conf=queue):
                with parse_context.accumulator.catchErrors():
                    layout.addQueue(queue)

        for template in parsed_config.project_templates:
            with parse_context.errorContext(stanza='project-template',
                                            conf=template):
                with parse_context.accumulator.catchErrors():
                    layout.addProjectTemplate(template)

        # The project stanzas containing a regex are separated from the normal
        # project stanzas and organized by regex. We need to loop over each
        # regex and copy each stanza below the regex for each matching project.
        for regex, config_projects in parsed_config.projects_by_regex.items():
            projects_matching_regex = tenant.getProjectsByRegex(regex)

            for trusted, project in projects_matching_regex:
                for config_project in config_projects:
                    # we just override the project name here so a simple copy
                    # should be enough
                    conf = config_project.copy()
                    name = project.canonical_name
                    conf.name = name
                    conf.freeze()
                    parsed_config.projects.append(conf)

        for project in parsed_config.projects:
            layout.addProjectConfig(project)

        # Now that all the project pipelines are loaded, fixup and
        # verify references to other config objects.
        self._validateProjectPipelineConfigs(tenant, layout, parse_context)

    def _validateProjectPipelineConfigs(self, tenant, layout, parse_context):
        # Validate references to other config objects
        def inner_validate_ppcs(ppc):
            for jobs in ppc.job_list.jobs.values():
                for job in jobs:
                    # validate that the job exists on its own (an
                    # additional requirement for project-pipeline
                    # jobs)
                    layout.getJob(job.name)
                    job.validateReferences(layout)

        for project_name in layout.project_configs:
            for project_config in layout.project_configs[project_name]:
                with parse_context.errorContext(stanza='project',
                                                conf=project_config):
                    with parse_context.accumulator.catchErrors():
                        for template_name in project_config.templates:
                            if template_name not in layout.project_templates:
                                raise TemplateNotFoundError(template_name)
                            project_templates = layout.getProjectTemplates(
                                template_name)
                            for p_tmpl in project_templates:
                                with parse_context.errorContext(
                                        stanza='project-template',
                                        conf=p_tmpl):
                                    acc = parse_context.accumulator
                                    with acc.catchErrors():
                                        for ppc in p_tmpl.pipelines.values():
                                            inner_validate_ppcs(ppc)
                        for ppc in project_config.pipelines.values():
                            inner_validate_ppcs(ppc)
            # Set a merge mode if we don't have one for this project.
            # This can happen if there are only regex project stanzas
            # but no specific project stanzas.
            (trusted, project) = tenant.getProject(project_name)
            project_metadata = layout.getProjectMetadata(project_name)
            tpc = tenant.project_configs[project.canonical_name]
            if project_metadata.merge_mode is None:
                mode = project.source.getProjectDefaultMergeMode(
                    project, valid_modes=tpc.merge_modes)
                project_metadata.merge_mode = model.MERGER_MAP[mode]
            if project_metadata.default_branch is None:
                default_branch = project.source.getProjectDefaultBranch(
                    project, tenant)
                project_metadata.default_branch = default_branch
            if tpc.merge_modes is not None:
                source_context = model.SourceContext(
                    project.canonical_name, project.name,
                    project.connection_name, None, None, trusted)
                with parse_context.errorContext(
                        source_context=source_context):
                    if project_metadata.merge_mode not in tpc.merge_modes:
                        mode = model.get_merge_mode_name(
                            project_metadata.merge_mode)
                        allowed_modes = list(map(model.get_merge_mode_name,
                                                 tpc.merge_modes))
                        err = Exception(f'Merge mode {mode} not supported '
                                        f'by project {project_name}. '
                                        f'Supported modes: {allowed_modes}.')
                        parse_context.accumulator.addError(err)

    def _parseLayout(self, tenant, data, parse_context, layout_uuid=None):
        # Don't call this method from dynamic reconfiguration because
        # it interacts with drivers and connections.
        layout = model.Layout(tenant, layout_uuid)
        layout.loading_errors = parse_context.loading_errors
        self.log.debug("Created layout id %s", layout.uuid)
        self._addLayoutItems(layout, tenant, data, parse_context)
        return layout


class ConfigLoader(object):
    log = logging.getLogger("zuul.ConfigLoader")

    def __init__(self, connections, zk_client, zuul_globals,
                 unparsed_config_cache, statsd=None, scheduler=None,
                 merger=None, keystorage=None):
        self.connections = connections
        self.zk_client = zk_client
        self.globals = zuul_globals
        self.scheduler = scheduler
        self.merger = merger
        self.keystorage = keystorage
        self.tenant_parser = TenantParser(
            connections, zk_client, scheduler, merger, keystorage,
            zuul_globals, statsd, unparsed_config_cache)
        self.authz_rule_parser = AuthorizationRuleParser()
        self.global_semaphore_parser = GlobalSemaphoreParser()
        self.api_root_parser = ApiRootParser()

    def expandConfigPath(self, config_path):
        if config_path:
            config_path = os.path.expanduser(config_path)
        if not os.path.exists(config_path):
            raise Exception("Unable to read tenant config file at %s" %
                            config_path)
        return config_path

    def readConfig(self, config_path, from_script=False,
                   tenants_to_validate=None):
        config_path = self.expandConfigPath(config_path)
        if not from_script:
            with open(config_path) as config_file:
                self.log.info("Loading configuration from %s" % (config_path,))
                data = yaml.safe_load(config_file)
        else:
            if not os.access(config_path, os.X_OK):
                self.log.error(
                    "Unable to read tenant configuration from a non "
                    "executable script (%s)" % config_path)
                data = []
            else:
                self.log.info(
                    "Loading configuration from script %s" % config_path)
                ret = subprocess.run(
                    [config_path], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                try:
                    ret.check_returncode()
                    data = yaml.safe_load(ret.stdout)
                except subprocess.CalledProcessError as error:
                    self.log.error(
                        "Tenant config script exec failed: %s (%s)" % (
                            str(error), str(ret.stderr)))
                    data = []
        unparsed_abide = model.UnparsedAbideConfig()
        unparsed_abide.extend(data)

        available_tenants = list(unparsed_abide.tenants)
        tenants_to_validate = tenants_to_validate or available_tenants
        if not set(tenants_to_validate).issubset(available_tenants):
            invalid = tenants_to_validate.difference(available_tenants)
            raise RuntimeError(f"Invalid tenant(s) found: {invalid}")
        for tenant_name in tenants_to_validate:
            # Validate the voluptuous schema early when reading the config
            # as multiple subsequent steps need consistent yaml input.
            self.tenant_parser.getSchema()(unparsed_abide.tenants[tenant_name])
        return unparsed_abide

    def loadAuthzRules(self, abide, unparsed_abide):
        abide.authz_rules.clear()
        for conf_authz_rule in unparsed_abide.authz_rules:
            authz_rule = self.authz_rule_parser.fromYaml(conf_authz_rule)
            abide.authz_rules[authz_rule.name] = authz_rule

    def loadSemaphores(self, abide, unparsed_abide):
        abide.semaphores.clear()
        for conf_semaphore in unparsed_abide.semaphores:
            semaphore = self.global_semaphore_parser.fromYaml(conf_semaphore)
            abide.semaphores[semaphore.name] = semaphore

    def loadTPCs(self, abide, unparsed_abide, tenants=None):
        # Load the global api root too
        if unparsed_abide.api_roots:
            api_root_conf = unparsed_abide.api_roots[0]
        else:
            api_root_conf = {}
        abide.api_root = self.api_root_parser.fromYaml(api_root_conf)

        if tenants:
            tenants_to_load = {t: unparsed_abide.tenants[t] for t in tenants
                               if t in unparsed_abide.tenants}
        else:
            tenants_to_load = unparsed_abide.tenants

        # Pre-load TenantProjectConfigs so we can get and cache all of a
        # project's config files (incl. tenant specific extra config) at once.
        with ThreadPoolExecutor(max_workers=4) as executor:
            for tenant_name, unparsed_config in tenants_to_load.items():
                tpc_registry = model.TenantTPCRegistry()
                config_tpcs, untrusted_tpcs = (
                    self.tenant_parser.loadTenantProjects(unparsed_config,
                                                          executor)
                )
                for tpc in config_tpcs:
                    tpc_registry.addConfigTPC(tpc)
                for tpc in untrusted_tpcs:
                    tpc_registry.addUntrustedTPC(tpc)
                # This atomic replacement of TPCs means that we don't need to
                # lock the abide.
                abide.setTPCRegistry(tenant_name, tpc_registry)

    def loadTenant(self, abide, tenant_name, ansible_manager, unparsed_abide,
                   min_ltimes=None, layout_uuid=None,
                   branch_cache_min_ltimes=None, ignore_cat_exception=True):
        """(Re-)load a single tenant.

        Description of cache stages:

        We have a local unparsed branch cache on each scheduler and the
        global config cache in Zookeeper. Depending on the event that
        triggers (re-)loading of a tenant we must make sure that those
        caches are considered valid or invalid correctly.

        If provided, the ``min_ltimes`` argument is expected to be a
        nested dictionary with the project-branches. The value defines
        the minimum logical time that is required for a cached config to
        be considered valid::

            {
                "example.com/org/project": {
                    "master": 12234,
                    "stable": -1,
                },
                "example.com/common-config": {
                    "master": -1,
                },
                ...
            }

        There are four scenarios to consider when loading a tenant.

        1. Processing a tenant reconfig event:
           - The min. ltime for the changed project(-branches) will be
             set to the event's ``zuul_event_ltime`` (to establish a
             happened-before relation in respect to the config change).
             The min. ltime for all other project-branches will be -1.
           - Config for needed project-branch(es) is updated via cat job
             if the cache is not valid (cache ltime < min. ltime).
           - Cache in Zookeeper and local unparsed branch cache is
             updated. The ltime of the cache will be the timestamp
             created shortly before requesting the config via the
             mergers (only for outdated items).
        2. Processing a FULL reconfiguration event:
           - The min. ltime for all project-branches is given as the
             ``zuul_event_ltime`` of the reconfiguration event.
           - Config for needed project-branch(es) is updated via cat job
             if the cache is not valid (cache ltime < min. ltime).
             Otherwise the local unparsed branch cache or the global
             config cache in Zookeeper is used.
           - Cache in Zookeeper and local unparsed branch cache is
             updated, with the ltime shortly before requesting the
             config via the mergers (only for outdated items).
        3. Processing a SMART reconfiguration event:
           - The min. ltime for all project-branches is given as -1 in
             order to use cached data wherever possible.
           - Config for new project-branch(es) is updated via cat job if
             the project is not yet cached. Otherwise the local unparsed
             branch cache or the global config cache in Zookeper is
             used.
           - Cache in Zookeeper and local unparsed branch cache is
             updated, with the ltime shortly before requesting the
             config via the mergers (only for new items).
        4. (Re-)loading a tenant due to a changed layout (happens after
           an event according to one of the other scenarios was
           processed on another scheduler):
           - The min. ltime for all project-branches is given as -1 in
             order to only use cached config.
           - Local unparsed branch cache is updated if needed.

        """
        if tenant_name not in unparsed_abide.tenants:
            # Copy tenants dictionary to not break concurrent iterations.
            with abide.tenant_lock:
                tenants = abide.tenants.copy()
                del tenants[tenant_name]
                abide.tenants = tenants
            return None

        unparsed_config = unparsed_abide.tenants[tenant_name]
        with ThreadPoolExecutor(max_workers=4) as executor:
            new_tenant = self.tenant_parser.fromYaml(
                abide, unparsed_config, ansible_manager, executor,
                min_ltimes, layout_uuid, branch_cache_min_ltimes,
                ignore_cat_exception)
        # Copy tenants dictionary to not break concurrent iterations.
        with abide.tenant_lock:
            tenants = abide.tenants.copy()
            tenants[tenant_name] = new_tenant
            abide.tenants = tenants
        if len(new_tenant.layout.loading_errors):
            self.log.warning(
                "%s errors detected during %s tenant configuration loading",
                len(new_tenant.layout.loading_errors), tenant_name)
            # Log accumulated errors
            for err in new_tenant.layout.loading_errors.errors[:10]:
                self.log.warning(err.error)
        return new_tenant

    def _loadDynamicProjectData(self, config, project, files,
                                additional_project_branches, trusted,
                                item, pcontext):
        tenant = item.pipeline.tenant
        tpc = tenant.project_configs[project.canonical_name]
        if trusted:
            branches = [tpc.load_branch if tpc.load_branch else 'master']
        else:
            # Use the cached branch list; since this is a dynamic
            # reconfiguration there should not be any branch changes.
            branches = tenant.getProjectBranches(project.canonical_name,
                                                 include_always_dynamic=True)
            # Except that we might be dealing with a change on a
            # dynamic branch which hasn't shown up in our cached list
            # yet (since we don't reconfigure on dynamic branch
            # creation).  Add additional branches in the queue which
            # match the dynamic branch regexes.
            additional_branches = list(additional_project_branches.get(
                project.canonical_name, []))
            additional_branches = [b for b in additional_branches
                                   if b not in branches
                                   and tpc.isAlwaysDynamicBranch(b)]
            if additional_branches:
                branches = branches + additional_branches

        for branch in branches:
            fns1 = []
            fns2 = []
            fns3 = []
            fns4 = []
            files_entry = files and files.connections.get(
                project.source.connection.connection_name, {}).get(
                    project.name, {}).get(branch)
            # If there is no files entry at all for this
            # project-branch, then use the cached config.
            if files_entry is None:
                incdata = tpc.parsed_branch_config.get(branch)
                if incdata:
                    config.extend(incdata)
                continue
            # Otherwise, do not use the cached config (even if the
            # files are empty as that likely means they were deleted).
            files_list = files_entry.keys()
            for fn in files_list:
                if fn.startswith("zuul.d/"):
                    fns1.append(fn)
                if fn.startswith(".zuul.d/"):
                    fns2.append(fn)
                for ef in tpc.extra_config_files:
                    if fn == ef:
                        fns3.append(fn)
                for ed in tpc.extra_config_dirs:
                    if fn.startswith(ed + '/'):
                        fns4.append(fn)
            fns = (["zuul.yaml"] + sorted(fns1) + [".zuul.yaml"] +
                   sorted(fns2) + fns3 + sorted(fns4))
            incdata = None
            loaded = None
            for fn in fns:
                data = files.getFile(project.source.connection.connection_name,
                                     project.name, branch, fn)
                if data:
                    source_context = model.SourceContext(
                        project.canonical_name, project.name,
                        project.connection_name, branch, fn, trusted,
                        tpc.implied_branch_matchers)
                    with pcontext.errorContext(source_context=source_context):
                        # Prevent mixing configuration source
                        conf_root = fn.split('/')[0]

                        # Don't load from more than one configuration in a
                        # project-branch (unless an "extra" file/dir).
                        if (conf_root in ZUUL_CONF_ROOT):
                            if loaded and loaded != conf_root:
                                self.log.warning(
                                    "Configuration in %s ignored because "
                                    "project-branch is already configured",
                                    source_context)
                                item.warning(
                                    "Configuration in %s ignored because "
                                    "project-branch is already configured" %
                                    source_context)
                                continue
                            loaded = conf_root

                        self.log.info(
                            "Loading configuration dynamically from %s" %
                            (source_context,))
                        incdata = self.tenant_parser.loadProjectYAML(
                            data, source_context, pcontext.accumulator)

                        if trusted:
                            incdata = self.tenant_parser.\
                                filterConfigProjectYAML(incdata)
                        else:
                            incdata = self.tenant_parser.\
                                filterUntrustedProjectYAML(incdata, pcontext)

                        config.extend(self.tenant_parser.parseConfig(
                            tenant, incdata, pcontext))

    def createDynamicLayout(self, item, files,
                            additional_project_branches,
                            ansible_manager,
                            include_config_projects=False,
                            zuul_event_id=None):
        tenant = item.pipeline.tenant
        log = get_annotated_logger(self.log, zuul_event_id)
        pcontext = ParseContext(self.connections, self.scheduler,
                                tenant, ansible_manager)
        if include_config_projects:
            config = model.ParsedConfig()
            for project in tenant.config_projects:
                self._loadDynamicProjectData(config, project, files,
                                             additional_project_branches,
                                             True, item, pcontext)
        else:
            config = tenant.config_projects_config.copy()

        for project in tenant.untrusted_projects:
            self._loadDynamicProjectData(config, project, files,
                                         additional_project_branches,
                                         False, item, pcontext)

        layout = model.Layout(tenant, item.layout_uuid)
        layout.loading_errors = pcontext.loading_errors
        log.debug("Created layout id %s", layout.uuid)
        if not include_config_projects:
            # NOTE: the actual pipeline objects (complete with queues
            # and enqueued items) are copied by reference here.  This
            # allows our shadow dynamic configuration to continue to
            # interact with all the other changes, each of which may
            # have their own version of reality.  We do not support
            # creating, updating, or deleting pipelines in dynamic
            # layout changes.
            layout.pipelines = tenant.layout.pipelines

            # NOTE: the semaphore definitions are copied from the
            # static layout here. For semaphores there should be no
            # per patch max value but exactly one value at any
            # time. So we do not support dynamic semaphore
            # configuration changes.
            layout.semaphores = tenant.layout.semaphores
            skip_pipelines = skip_semaphores = True
        else:
            skip_pipelines = skip_semaphores = False

        self.tenant_parser._addLayoutItems(layout, tenant, config,
                                           pcontext,
                                           skip_pipelines=skip_pipelines,
                                           skip_semaphores=skip_semaphores)
        return layout
