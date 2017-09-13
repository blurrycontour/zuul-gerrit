#!/usr/bin/env python

# Copyright 2017 Red Hat, Inc.
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

# TODO(mordred):
# * Read and apply filters from the jobs: section
# * Figure out shared job queues
# * Emit job definitions
#   * figure out from builders whether or not it's a normal job or a
#     a devstack-legacy job
#   * Handle emitting arbitrary tox jobs (see tox-py27dj18)

import argparse
import collections
import copy
import itertools
import logging
import os
import re
from typing import Any, Dict, List, Optional  # flake8: noqa

import jenkins_jobs.builder
from jenkins_jobs.formatter import deep_format
import jenkins_jobs.formatter
from jenkins_jobs.parser import matches
import jenkins_jobs.parser
import yaml

JOBS_BY_ORIG_TEMPLATE = {}
SUFFIXES = []
DESCRIPTION = """Migrate zuul v2 and Jenkins Job Builder to Zuul v3.

This program takes a zuul v2 layout.yaml and a collection of Jenkins Job
Builder job definitions and transforms them into a Zuul v3 config. An
optional mapping config can be given that defines how to map old jobs
to new jobs.
"""
def project_representer(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map',
                                    data.items())


def construct_yaml_map(self, node):
    data = collections.OrderedDict()
    yield data
    value = self.construct_mapping(node)

    if isinstance(node, yaml.MappingNode):
        self.flatten_mapping(node)
    else:
        raise yaml.constructor.ConstructorError(
            None, None,
            'expected a mapping node, but found %s' % node.id,
            node.start_mark)

    mapping = collections.OrderedDict()
    for key_node, value_node in node.value:
        key = self.construct_object(key_node, deep=False)
        try:
            hash(key)
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                'while constructing a mapping', node.start_mark,
                'found unacceptable key (%s)' % exc, key_node.start_mark)
        value = self.construct_object(value_node, deep=False)
        mapping[key] = value
    data.update(mapping)


class IndentedEmitter(yaml.emitter.Emitter):
    def expect_block_sequence(self):
        self.increase_indent(flow=False, indentless=False)
        self.state = self.expect_first_block_sequence_item


class IndentedDumper(IndentedEmitter, yaml.serializer.Serializer,
                     yaml.representer.Representer, yaml.resolver.Resolver):
    def __init__(self, stream,
                 default_style=None, default_flow_style=None,
                 canonical=None, indent=None, width=None,
                 allow_unicode=None, line_break=None,
                 encoding=None, explicit_start=None, explicit_end=None,
                 version=None, tags=None):
        IndentedEmitter.__init__(
            self, stream, canonical=canonical,
            indent=indent, width=width,
            allow_unicode=allow_unicode,
            line_break=line_break)
        yaml.serializer.Serializer.__init__(
            self, encoding=encoding,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
            version=version, tags=tags)
        yaml.representer.Representer.__init__(
            self, default_style=default_style,
            default_flow_style=default_flow_style)
        yaml.resolver.Resolver.__init__(self)


def ordered_load(stream, *args, **kwargs):
    return yaml.load(stream=stream, *args, **kwargs)

def ordered_dump(data, stream=None, *args, **kwargs):
    dumper = IndentedDumper
    # We need to do this because of how template expasion into a project
    # works. Without it, we end up with YAML references to the expanded jobs.
    dumper.ignore_aliases = lambda self, data: True

    return yaml.dump(data, stream=stream, default_flow_style=False,
                     Dumper=dumper, width=80, *args, **kwargs)

def get_single_key(var):
    if isinstance(var, str):
        return var
    elif isinstance(var, list):
        return var[0]
    return list(var.keys())[0]


def has_single_key(var):
    if isinstance(var, list):
        return len(var) == 1
    if isinstance(var, str):
        return True
    dict_keys = list(var.keys())
    if len(dict_keys) != 1:
        return False
    if var[get_single_key(var)]:
        return False
    return True


def combination_matches(combination, match_combinations):
    """
    Checks if the given combination is matches for any of the given combination
    globs, being those a set of combinations where if a key is missing, it's
    considered matching

    (key1=2, key2=3)

    would match the combination match:
    (key2=3)

    but not:
    (key1=2, key2=2)
    """
    for cmatch in match_combinations:
        for key, val in combination.items():
            if cmatch.get(key, val) != val:
                break
        else:
            return True
    return False


def expandYamlForTemplateJob(self, project, template, jobs_glob=None):
    dimensions = []
    template_name = template['name']
    orig_template = copy.deepcopy(template)

    # reject keys that are not useful during yaml expansion
    for k in ['jobs']:
        project.pop(k)
    excludes = project.pop('exclude', [])
    for (k, v) in project.items():
        tmpk = '{{{0}}}'.format(k)
        if tmpk not in template_name:
            continue
        if type(v) == list:
            dimensions.append(zip([k] * len(v), v))
    # XXX somewhat hackish to ensure we actually have a single
    # pass through the loop
    if len(dimensions) == 0:
        dimensions = [(("", ""),)]

    for values in itertools.product(*dimensions):
        params = copy.deepcopy(project)
        params = self.applyDefaults(params, template)

        expanded_values = {}
        for (k, v) in values:
            if isinstance(v, dict):
                inner_key = next(iter(v))
                expanded_values[k] = inner_key
                expanded_values.update(v[inner_key])
            else:
                expanded_values[k] = v

        params.update(expanded_values)
        params = deep_format(params, params)
        if combination_matches(params, excludes):
            log = logging.getLogger("zuul.Migrate.YamlParser")
            log.debug('Excluding combination %s', str(params))
            continue

        allow_empty_variables = self.config \
            and self.config.has_section('job_builder') \
            and self.config.has_option(
                'job_builder', 'allow_empty_variables') \
            and self.config.getboolean(
                'job_builder', 'allow_empty_variables')

        for key in template.keys():
            if key not in params:
                params[key] = template[key]

        params['template-name'] = template_name
        project_name = params['name']
        params['name'] = '$ZUUL_SHORT_PROJECT_NAME'
        expanded = deep_format(template, params, allow_empty_variables)

        job_name = expanded.get('name')
        templated_job_name = job_name
        if job_name:
            job_name = job_name.replace(
                '$ZUUL_SHORT_PROJECT_NAME', project_name)
            expanded['name'] = job_name
        if jobs_glob and not matches(job_name, jobs_glob):
            continue

        self.formatDescription(expanded)
        expanded['orig_template'] = orig_template
        expanded['template_name'] = template_name
        self.jobs.append(expanded)
        JOBS_BY_ORIG_TEMPLATE[templated_job_name] = expanded

jenkins_jobs.parser.YamlParser.expandYamlForTemplateJob = expandYamlForTemplateJob


class JJB(jenkins_jobs.builder.Builder):
    def __init__(self):
        self.global_config = None
        self._plugins_list = []

    def expandComponent(self, component_type, component, template_data):
        component_list_type = component_type + 's'
        new_components = []
        if isinstance(component, dict):
            name, component_data = next(iter(component.items()))
            if template_data:
                component_data = jenkins_jobs.formatter.deep_format(
                    component_data, template_data, True)
        else:
            name = component
            component_data = {}

        new_component = self.parser.data.get(component_type, {}).get(name)
        if new_component:
            for new_sub_component in new_component[component_list_type]:
                new_components.extend(
                    self.expandComponent(component_type,
                                         new_sub_component, component_data))
        else:
            new_components.append({name: component_data})
        return new_components

    def expandMacros(self, job):
        for component_type in ['builder', 'publisher', 'wrapper']:
            component_list_type = component_type + 's'
            new_components = []
            for new_component in job.get(component_list_type, []):
                new_components.extend(self.expandComponent(component_type,
                                                           new_component, {}))
            job[component_list_type] = new_components


class OldProject:
    def __init__(self, name, gate_jobs):
        self.name = name
        self.gate_jobs = gate_jobs


class OldJob:
    def __init__(self, name):
        self.name = name
        self.queue_name = None

    def __repr__(self):
        return self.name


class Job:

    def __init__(self,
                 orig: str,
                 name: str=None,
                 content: Dict[str, Any]=None,
                 vars: Dict[str, str]=None,
                 required_projects: List[str]=None,
                 nodes: List[str]=None,
                 parent=None) -> None:
        self.orig = orig
        self.voting = True
        self.name = name
        self.content = content.copy() if content else None
        self.vars = vars or {}
        self.required_projects = required_projects or []
        self.nodes = nodes or []
        self.parent = parent
        self.branch = None
        self.files = None
        self.jjb_job = None

        if self.content and not self.name:
            self.name = get_single_key(content)
        if not self.name:
            self.name = self.orig
        self.name = self.name.replace('-{name}', '').replace('{name}-', '')

        for suffix in SUFFIXES:
            suffix = '-{suffix}'.format(suffix=suffix)

            if self.name.endswith(suffix):
                self.name = self.name.replace(suffix, '')

    def _stripNodeName(self, node):
        node_key = '-{node}'.format(node=node)
        self.name = self.name.replace(node_key, '')

    def setVars(self, vars):
        self.vars = vars

    def setRequiredProjects(self, required_projects):
        self.required_projects = required_projects

    def setParent(self, parent):
        self.parent = parent

    def extractNode(self, default_node, labels):
        matching_label = None
        for label in labels:
            if label in self.orig:
                if not matching_label:
                    matching_label = label
                elif len(label) > len(matching_label):
                    matching_label = label

        if matching_label:
            if matching_label == default_node:
                self._stripNodeName(matching_label)
            else:
                self.nodes.append(matching_label)

    def getDepends(self):
        return [self.parent.name]

    def getNodes(self):
        return self.nodes

    def addJJBJob(self, jobs):
        if '{name}' in self.orig:
            self.jjb_job = JOBS_BY_ORIG_TEMPLATE[self.orig.format(
                name='$ZUUL_SHORT_PROJECT_NAME')]
        else:
            self.jjb_job = jobs[self.orig]

    def getTimeout(self):
        if self.jjb_job:
            for wrapper in self.jjb_job.get('wrappers', []):
                if isinstance(wrapper, dict):
                    build_timeout = wrapper.get('timeout')
                    if isinstance(build_timeout, dict):
                        timeout = build_timeout.get('timeout')
                        if timeout is not None:
                            timeout = int(timeout) * 60

    def toJobDict(self):
        output = collections.OrderedDict()
        output['name'] = self.name

        if self.vars:
            output['vars'] = self.vars.copy()
        timeout = self.getTimeout()
        if timeout:
            output['timeout'] = timeout
            output['vars']['BUILD_TIMEOUT'] = str(timeout * 1000)

        if self.nodes:
            output['nodes'] = self.getNodes()

        if self.required_projects:
            output['required-projects'] = self.required_projects

        return output

    def toPipelineDict(self):
        if self.content:
            output = self.content
        else:
            output = collections.OrderedDict()
            output[self.name] = collections.OrderedDict()

        if self.parent:
            output[self.name].setdefault('dependencies', self.getDepends())

        if not self.voting:
            output[self.name].setdefault('voting', False)

        if self.required_projects:
            output[self.name].setdefault(
                'required-projects', self.required_projects)

        if self.vars:
            job_vars = output[self.name].get('vars', collections.OrderedDict())
            job_vars.update(self.vars)

        if self.branch:
            output[self.name]['branch'] = self.branch

        if self.files:
            output[self.name]['files'] = self.files

        if not output[self.name]:
            return self.name

        return output


class JobMapping:
    log = logging.getLogger("zuul.Migrate.JobMapping")

    def __init__(self, nodepool_config, layout, mapping_file=None):
        self.layout = layout
        self.job_direct = {}
        self.labels = []
        self.job_mapping = []
        self.template_mapping = {}
        self.jjb_jobs = {}
        self.seen_new_jobs = []
        nodepool_data = ordered_load(open(nodepool_config, 'r'))
        for label in nodepool_data['labels']:
            self.labels.append(label['name'])
        if not mapping_file:
            self.default_node = 'ubuntu-xenial'
        else:
            mapping_data = ordered_load(open(mapping_file, 'r'))
            self.default_node = mapping_data['default-node']
            global SUFFIXES
            SUFFIXES = mapping_data.get('strip-suffixes', [])
            for map_info in mapping_data.get('job-mapping', []):
                if map_info['old'].startswith('^'):
                    map_info['pattern'] = re.compile(map_info['old'])
                    self.job_mapping.append(map_info)
                else:
                    self.job_direct[map_info['old']] = map_info['new']

            for map_info in mapping_data.get('template-mapping', []):
                self.template_mapping[map_info['old']] = map_info['new']

    def makeNewName(self, new_name, match_dict):
        return new_name.format(**match_dict)

    def hasProjectTemplate(self, old_name):
        return old_name in self.template_mapping

    def setJJBJobs(self, jjb_jobs):
        self.jjb_jobs = jjb_jobs

    def getNewTemplateName(self, old_name):
        return self.template_mapping.get(old_name, old_name)

    def mapNewJob(self, name, info) -> Optional[Job]:
        matches = info['pattern'].search(name)
        if not matches:
            return None
        match_dict = matches.groupdict()
        if isinstance(info['new'], dict):
            job = Job(orig=name, content=info['new'])
        else:
            job = Job(orig=name, name=info['new'].format(**match_dict))

        if 'vars' in info:
            job.setVars(self._expandVars(info, match_dict))

        if 'required-projects' in info:
            job.setRequiredProjects(
                self._expandRequiredProjects(info, match_dict))

        return job

    def _expandVars(self, info, match_dict):
        job_vars = info['vars'].copy()
        for key in job_vars.keys():
            job_vars[key] = job_vars[key].format(**match_dict)
        return job_vars

    def _expandRequiredProjects(self, info, match_dict):
        required_projects = []
        job_projects = info['required-projects'].copy()
        for project in job_projects:
            required_projects.append(project.format(**match_dict))
        return required_projects

    def getNewJob(self, job_name, remove_gate):
        if job_name in self.job_direct:
            if isinstance(self.job_direct[job_name], dict):
                return Job(job_name, content=self.job_direct[job_name])
            else:
                if job_name not in self.seen_new_jobs:
                    self.seen_new_jobs.append(self.job_direct[job_name])
                return Job(job_name, name=self.job_direct[job_name])

        new_job = None
        for map_info in self.job_mapping:
            new_job = self.mapNewJob(job_name, map_info)
            if new_job:
                if job_name not in self.seen_new_jobs:
                    self.seen_new_jobs.append(new_job.name)
                break
        if not new_job:
            orig_name = job_name
            if remove_gate:
                job_name = job_name.replace('gate-', '', 1)
            job_name = 'legacy-{job_name}'.format(job_name=job_name)
            new_job = Job(orig=orig_name, name=job_name)

        new_job.extractNode(self.default_node, self.labels)

        # Handle matchers
        for layout_job in self.layout.get('jobs', []):
            if re.search(layout_job['name'], new_job.orig):
                # Matchers that can apply to templates must be processed first
                # since project-specific matchers can cause the template to
                # be expanded into a project.
                if not layout_job.get('voting', True):
                    new_job.voting = False
                if layout_job.get('branch'):
                    new_job.branch = layout_job['branch']
                if layout_job.get('files'):
                    new_job.files = layout_job['files']

        new_job.addJJBJob(self.jjb_jobs)
        return new_job

class ChangeQueue:
    def __init__(self):
        self.name = ''
        self.assigned_name = None
        self.generated_name = None
        self.projects = []
        self._jobs = set()

    def getJobs(self):
        return self._jobs

    def getProjects(self):
        return [p.name for p in self.projects]

    def addProject(self, project):
        if project not in self.projects:
            self.projects.append(project)
            self._jobs |= project.gate_jobs

            names = [x.name for x in self.projects]
            names.sort()
            self.generated_name = names[0].split('/')[-1]

            for job in self._jobs:
                if job.queue_name:
                    if (self.assigned_name and
                        job.queue_name != self.assigned_name):
                        raise Exception("More than one name assigned to "
                                        "change queue: %s != %s" %
                                        (self.assigned_name,
                                         job.queue_name))
                    self.assigned_name = job.queue_name
            self.name = self.assigned_name or self.generated_name

    def mergeChangeQueue(self, other):
        for project in other.projects:
            self.addProject(project)

class ZuulMigrate:

    log = logging.getLogger("zuul.Migrate")

    def __init__(self, layout, job_config, nodepool_config,
                 outdir, mapping, move):
        self.layout = ordered_load(open(layout, 'r'))
        self.job_config = job_config
        self.outdir = outdir
        self.mapping = JobMapping(nodepool_config, self.layout, mapping)
        self.move = move

        self.jobs = {}
        self.old_jobs = {}
        self.job_objects = []
        self.new_templates = {}

    def run(self):
        self.loadJobs()
        self.buildChangeQueues()
        self.convertJobs()
        self.writeJobs()

    def loadJobs(self):
        self.log.debug("Loading jobs")
        builder = JJB()
        builder.load_files([self.job_config])
        builder.parser.expandYaml()
        unseen = set(self.jobs.keys())
        for job in builder.parser.jobs:
            builder.expandMacros(job)
            self.jobs[job['name']] = job
            unseen.discard(job['name'])
        for name in unseen:
            del self.jobs[name]
        self.mapping.setJJBJobs(self.jobs)

    def getOldJob(self, name):
        if name not in self.old_jobs:
            self.old_jobs[name] = OldJob(name)
        return self.old_jobs[name]

    def flattenOldJobs(self, tree, name=None):
        if isinstance(tree, str):
            n = tree.format(name=name)
            return [self.getOldJob(n)]

        new_list = []  # type: ignore
        if isinstance(tree, list):
            for job in tree:
                new_list.extend(self.flattenOldJobs(job, name))
        elif isinstance(tree, dict):
            parent_name = get_single_key(tree)
            jobs = self.flattenOldJobs(tree[parent_name], name)
            for job in jobs:
                new_list.append(self.getOldJob(job))
            new_list.append(self.getOldJob(parent_name))
        return new_list

    def buildChangeQueues(self):
        self.log.debug("Building shared change queues")

        for j in self.layout['jobs']:
            if '^' in j['name'] or '$' in j['name']:
                continue
            job = self.getOldJob(j['name'])
            job.queue_name = j.get('queue-name')

        change_queues = []

        for project in self.layout.get('projects'):
            if 'gate' not in project:
                continue
            gate_jobs = set()
            for template in project['template']:
                for pt in self.layout.get('project-templates'):
                    if pt['name'] != template['name']:
                        continue
                    if 'gate' not in pt['name']:
                        continue
                    gate_jobs |= set(self.flattenOldJobs(pt['gate'], project['name']))
            gate_jobs |= set(self.flattenOldJobs(project['gate']))
            old_project = OldProject(project['name'], gate_jobs)
            change_queue = ChangeQueue()
            change_queue.addProject(old_project)
            change_queues.append(change_queue)
            self.log.debug("Created queue: %s" % change_queue)

        # Iterate over all queues trying to combine them, and keep doing
        # so until they can not be combined further.
        last_change_queues = change_queues
        while True:
            new_change_queues = self.combineChangeQueues(last_change_queues)
            if len(last_change_queues) == len(new_change_queues):
                break
            last_change_queues = new_change_queues

        self.log.debug("  Shared change queues:")
        for queue in new_change_queues:
            self.log.debug("    %s containing %s" % (
                queue, queue.generated_name))
        self.change_queues = new_change_queues

    def combineChangeQueues(self, change_queues):
        self.log.debug("Combining shared queues")
        new_change_queues = []
        for a in change_queues:
            merged_a = False
            for b in new_change_queues:
                if not a.getJobs().isdisjoint(b.getJobs()):
                    self.log.debug("Merging queue %s into %s" % (a, b))
                    b.mergeChangeQueue(a)
                    merged_a = True
                    break  # this breaks out of 'for b' and continues 'for a'
            if not merged_a:
                self.log.debug("Keeping queue %s" % (a))
                new_change_queues.append(a)
        return new_change_queues

    def convertJobs(self):
        pass

    def setupDir(self):
        zuul_yaml = os.path.join(self.outdir, 'zuul.yaml')
        zuul_d = os.path.join(self.outdir, 'zuul.d')
        orig = os.path.join(zuul_d, '01zuul.yaml')
        outfile = os.path.join(zuul_d, '99converted.yaml')
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir)
        if not os.path.exists(zuul_d):
            os.makedirs(zuul_d)
        if os.path.exists(zuul_yaml) and self.move:
            os.rename(zuul_yaml, orig)
        return outfile

    def makeNewJobs(self, old_job, parent: Job=None):
        self.log.debug("makeNewJobs(%s)", old_job)
        if isinstance(old_job, str):
            remove_gate = True
            if old_job.startswith('gate-'):
                # Check to see if gate- and bare versions exist
                if old_job.replace('gate-', '', 1) in self.jobs:
                    remove_gate = False
            job = self.mapping.getNewJob(old_job, remove_gate)
            if parent:
                job.setParent(parent)
            return [job]

        new_list = []  # type: ignore
        if isinstance(old_job, list):
            for job in old_job:
                new_list.extend(self.makeNewJobs(job, parent=parent))

        elif isinstance(old_job, dict):
            parent_name = get_single_key(old_job)
            parent = Job(orig=parent_name, parent=parent)

            jobs = self.makeNewJobs(old_job[parent_name], parent=parent)
            for job in jobs:
                new_list.append(job)
            new_list.append(parent)
        return new_list

    def writeProjectTemplate(self, template):
        new_template = collections.OrderedDict()
        if 'name' in template:
            new_template['name'] = template['name']
        for key, value in template.items():
            if key == 'name':
                continue

            # keep a cache of the Job objects so we can use it to get old
            # job name to new job name when expanding templates into projects.
            tmp = [job for job in self.makeNewJobs(value)]
            self.job_objects.extend(tmp)
            jobs = [job.toPipelineDict() for job in tmp]
            new_template[key] = dict(jobs=jobs)

        return new_template

    def scanForProjectMatchers(self, project_name):
        ''' Get list of job matchers that reference the given project name '''
        job_matchers = []
        for matcher in self.layout.get('jobs', []):
            for skipper in matcher.get('skip-if', []):
                if skipper.get('project'):
                    if re.search(skipper['project'], project_name):
                        job_matchers.append(matcher)
        return job_matchers

    def findReferencedTemplateNames(self, job_matchers, project_name):
        ''' Search templates in the layout file for matching jobs '''
        template_names = []

        def search_jobs(template):
            def _search(job):
                if isinstance(job, str):
                    for matcher in job_matchers:
                        if re.search(matcher['name'],
                                     job.format(name=project_name)):
                            template_names.append(template['name'])
                            return True
                elif isinstance(job, list):
                    for i in job:
                        if _search(i):
                            return True
                elif isinstance(job, dict):
                    for k, v in job.items():
                        if _search(k) or _search(v):
                            return True
                return False

            for key, value in template.items():
                if key == 'name':
                    continue
                for job in template[key]:
                    if _search(job):
                        return

        for template in self.layout.get('project-templates', []):
            search_jobs(template)
        return template_names

    def expandTemplateIntoProject(self, template_name, project):
        self.log.debug("EXPAND template %s into project %s",
                       template_name, project['name'])
        # find the new template since that's the thing we're expanding
        if template_name not in self.new_templates:
            self.log.error(
                "Template %s not found for expansion into project %s",
                template_name, project['name'])
            return

        template = self.new_templates[template_name]

        for pipeline, value in template.items():
            if pipeline == 'name':
                continue
            if pipeline not in project:
                project[pipeline] = dict(jobs=[])
            project[pipeline]['jobs'].extend(value['jobs'])

    def getOldJobName(self, new_job_name):
        for job in self.job_objects:
            if job.name == new_job_name:
                return job.orig
        return None

    def applyProjectMatchers(self, matchers, project):
        '''
        Apply per-project job matchers to the given project.

        :param matchers: Job matchers that referenced the given project.
        :param project: The new project object.
        '''

        def processPipeline(pipeline_jobs, job_name_regex, files):
            for job in pipeline_jobs:
                if isinstance(job, str):
                    old_job_name = self.getOldJobName(job)
                    if not old_job_name:
                        continue
                    if re.search(job_name_regex, old_job_name):
                        self.log.debug(
                            "Applied irrelevant-files to job %s in project %s",
                            job, project['name'])
                        job = dict(job={'irrelevant-files': files})
                elif isinstance(job, dict):
                    # should really only be one key (job name)
                    job_name = list(job.keys())[0]
                    extras = job[job_name]
                    old_job_name = self.getOldJobName(job_name)
                    if not old_job_name:
                        continue
                    if re.search(job_name_regex, old_job_name):
                        self.log.debug(
                            "Applied irrelevant-files to complex job "
                            "%s in project %s", job_name, project['name'])
                        if 'irrelevant-files' not in extras:
                            extras['irrelevant-files'] = []
                        extras['irrelevant-files'].extend(files)

        def applyIrrelevantFiles(job_name_regex, files):
            for k, v in project.items():
                if k in ('template', 'name'):
                    continue
                processPipeline(project[k]['jobs'], job_name_regex, files)
            
        for matcher in matchers:
            # find the project-specific section
            for skipper in matcher.get('skip-if', []):
                if skipper.get('project'):
                    if re.search(skipper['project'], project['name']):
                       if 'all-files-match-any' in skipper:
                           applyIrrelevantFiles(matcher['name'],
                                                skipper['all-files-match-any'])

    def writeProject(self, project):
        '''
        Create a new v3 project definition.

        As part of creating the project, scan for project-specific job matchers
        referencing this project and remove the templates matching the job
        regex for that matcher. Expand the matched template(s) into the project
        so we can apply the project-specific matcher to the job(s).
        '''
        new_project = collections.OrderedDict()
        if 'name' in project:
            new_project['name'] = project['name']

        job_matchers = self.scanForProjectMatchers(project['name'])
        if job_matchers:
            exp_template_names = self.findReferencedTemplateNames(
                job_matchers, project['name'])
        else:
            exp_template_names = []

        templates_to_expand = []
        if 'template' in project:
            new_project['template'] = []
            for template in project['template']:
                if template['name'] in exp_template_names:
                    templates_to_expand.append(template['name'])
                    continue
                new_project['template'].append(dict(
                    name=self.mapping.getNewTemplateName(template['name'])))

        for key, value in project.items():
            if key in ('name', 'template'):
                continue
            else:
                new_project[key] = collections.OrderedDict()
                if key == 'gate':
                    for queue in self.change_queues:
                        if project['name'] not in queue.getProjects():
                            continue
                        if len(queue.getProjects()) == 1:
                            continue
                        new_project[key]['queue'] = queue.name
                tmp = [job for job in self.makeNewJobs(value)]
                self.job_objects.extend(tmp)
                jobs = [job.toPipelineDict() for job in tmp]
                new_project[key]['jobs'] = jobs

        for name in templates_to_expand:
            self.expandTemplateIntoProject(name, new_project)

        # Need a deep copy after expansion, else our templates end up
        # also getting this change.
        new_project = copy.deepcopy(new_project)
        self.applyProjectMatchers(job_matchers, new_project)

        return new_project

    def writeJobs(self):
        outfile = self.setupDir()
        config = []

        for template in self.layout.get('project-templates', []):
            self.log.debug("Processing template: %s", template)
            if not self.mapping.hasProjectTemplate(template['name']):
                new_template = self.writeProjectTemplate(template)
                self.new_templates[new_template['name']] = new_template
                config.append({'project-template': new_template})

        for project in self.layout.get('projects', []):
            config.append(
                {'project': self.writeProject(project)})

        seen_jobs = []
        for job in self.job_objects:
            if (job.name not in seen_jobs
                    and job.name not in self.mapping.seen_new_jobs):
                config.append({'job': job.toJobDict()})
                seen_jobs.append(job.name)

        with open(outfile, 'w') as yamlout:
            # Insert an extra space between top-level list items
            yamlout.write(ordered_dump(config).replace('\n-', '\n\n-'))


def main():
    yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                         construct_yaml_map)

    yaml.add_representer(collections.OrderedDict, project_representer,
                         Dumper=IndentedDumper)

    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        'layout',
        help="The Zuul v2 layout.yaml file to read.")
    parser.add_argument(
        'job_config',
        help="Directory containing Jenkins Job Builder job definitions.")
    parser.add_argument(
        'nodepool_config',
        help="Nodepool config file containing complete set of node names")
    parser.add_argument(
        'outdir',
        help="A directory into which the Zuul v3 config will be written.")
    parser.add_argument(
        '--mapping',
        default=None,
        help="A filename with a yaml mapping of old name to new name.")
    parser.add_argument(
        '-v', dest='verbose', action='store_true', help='verbose output')
    parser.add_argument(
        '-m', dest='move', action='store_true',
        help='Move zuul.yaml to zuul.d if it exists')

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    ZuulMigrate(args.layout, args.job_config, args.nodepool_config,
                args.outdir, args.mapping, args.move).run()


if __name__ == '__main__':
    main()
