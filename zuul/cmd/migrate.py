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

import argparse
import collections
import logging
import os
import re
from typing import Any, Dict, List, Optional  # flake8: noqa

import jenkins_jobs.builder
import jenkins_jobs.formatter

from zuul.lib import yamlutil

DESCRIPTION = """Migrate zuul v2 and Jenkins Job Builder to Zuul v3.

This program takes a zuul v2 layout.yaml and a collection of Jenkins Job
Builder job definitions and transforms them into a Zuul v3 config. An
optional mapping config can be given that defines how to map old jobs
to new jobs.
"""
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
    if var[get_single_key(from_dict)]:
        return False
    return True


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


class Job:

    def __init__(self,
                 orig: str,
                 name: str=None,
                 content: Dict[str, Any]=None,
                 vars: Dict[str, str]=None,
                 nodes: List[str]=None,
                 parent=None):
        self.orig = orig
        self.name = name
        self.content = content.copy() if content else None
        self.vars = vars or {}
        self.nodes = nodes or []
        self.parent = parent

        if self.content and not self.name:
            self.name = get_single_key(content)
        if not self.name:
            self.name = self.orig.replace('-{name}', '').replace('{name}-', '')

    def _stripNodeName(self, node):
        node_key = '-{node}'.format(node=node)
        self.name = self.name.replace(node_key, '')

    def setVars(self, vars):
        self.vars = vars

    def setParent(self, parent):
        self.parent = parent

    def extractNode(self, default_node, labels):
        if default_node in self.name:
            self._stripNodeName(default_node)
        else:
            for label in labels:
                if label in self.name:
                    self._stripNodeName(label)
                    self.nodes.append(label)

    def getDepends(self):
        return [self.parent.name]

    def getNodes(self):
        return [{'node': node, 'label': node} for node in self.nodes]

    def toDict(self):
        if self.content:
            output = self.content
        else:
            output = collections.OrderedDict()
            output[self.name] = collections.OrderedDict()

        if self.parent:
            output[self.name].setdefault('dependencies', self.getDepends())

        if self.nodes:
            output[self.name].setdefault('nodes', self.getNodes())

        if self.vars:
            job_vars = output[self.name].get('vars', collections.OrderedDict())
            job_vars.update(self.vars)

        if not output[self.name]:
            return self.name
        return output


class JobMapping:
    log = logging.getLogger("zuul.Migrate.JobMapping")

    def __init__(self, nodepool_config, mapping_file=None):
        self.direct = {}
        self.labels = []
        self.mapping = []
        nodepool_data = yamlutil.ordered_load(open(nodepool_config, 'r'))
        for label in nodepool_data['labels']:
            self.labels.append(label['name'])
        if not mapping_file:
            self.default_node = 'ubuntu-xenial'
        else:
            mapping_data = yamlutil.ordered_load(open(mapping_file, 'r'))
            self.default_node = mapping_data['default-node']
            for map_info in mapping_data['mapping']:
                if map_info['old'].startswith('^'):
                    map_info['pattern'] = re.compile(map_info['old'])
                    self.mapping.append(map_info)
                else:
                    self.direct[map_info['old']] = map_info['new']

    def makeNewName(self, new_name, match_dict):
        return new_name.format(**match_dict)

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
            job_vars = info['vars'].copy()
            for key in job_vars.keys():
                job_vars[key] = job_vars[key].format(**match_dict)
            job.setVars(job_vars)

        return job

    def getNewJob(self, job_name):
        if job_name in self.direct:
            return Job(job_name, content=self.direct[job_name])

        new_job = None
        for map_info in self.mapping:
            new_job = self.mapNewJob(job_name, map_info)
            if new_job:
                break
        if not new_job:
            new_job = Job(job_name)

        new_job.extractNode(self.default_node, self.labels)
        return new_job


class ZuulMigrate:

    log = logging.getLogger("zuul.Migrate")

    def __init__(self, layout, job_config, nodepool_config, outdir, mapping):
        self.layout = yamlutil.ordered_load(open(layout, 'r'))
        self.job_config = job_config
        self.outdir = outdir
        self.mapping = JobMapping(nodepool_config, mapping)

        self.jobs = {}

    def run(self):
        #self.loadJobs()
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
        if os.path.exists(zuul_yaml):
            os.rename(zuul_yaml, orig)
        return outfile

    def makeNewJobs(self, old_job, parent: Job=None):
        self.log.debug("makeNewJobs(%s)", old_job)
        if isinstance(old_job, str):
            job = self.mapping.getNewJob(old_job)
            if parent:
                job.setParent(parent)
            return [job]

        new_list = []
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
        for key in ('name',):
            if key in template:
                new_template[key] = template[key]
        for key, value in template.items():
            if key == 'name':
                new_template[key] = value
            else:
                jobs = [job.toDict() for job in self.makeNewJobs(value)]
                new_template[key] = jobs

        return new_template

    def writeProject(self, project):
        new_project = collections.OrderedDict()
        for key in ('name', 'template'):
            if key in project:
                new_project[key] = project[key]
        for key, value in project.items():
            if key in ('name', 'template'):
                continue
            else:
                jobs = [job.toDict() for job in self.makeNewJobs(value)]
                new_project[key] = jobs

        return new_project

    def writeJobs(self):
        outfile = self.setupDir()
        config = []
        for template in self.layout.get('project-templates', []):
            self.log.debug("Processing template: %s", template)
            config.append(
                {'project-template': self.writeProjectTemplate(template)})

        for project in self.layout.get('projects', []):
            config.append(
                {'project': self.writeProject(project)})
        with open(outfile, 'w') as yamlout:
            # Insert an extra space between top-level list items
            yamlout.write(
                yamlutil.ordered_dump(config).replace('\n-', '\n\n-'))


def main():
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

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    ZuulMigrate(args.layout, args.job_config, args.nodepool_config,
                args.outdir, args.mapping).run()


if __name__ == '__main__':
    main()
