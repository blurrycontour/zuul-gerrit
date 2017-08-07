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
import logging
import os
import re

import jenkins_jobs.builder
import jenkins_jobs.formatter
import yaml

DESCRIPTION = """Migrate zuul v2 and Jenkins Job Builder to Zuul v3.

This program takes a zuul v2 layout.yaml and a collection of Jenkins Job
Builder job definitions and transforms them into a Zuul v3 config. An
optional mapping config can be given that defines how to map old jobs
to new jobs.
"""

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


class JobMapping:
    log = logging.getLogger("zuul.Migrate.JobMapping")

    def __init__(self, mapping_file=None):
        if not mapping_file:
            self.mapping = []
        else:
            self.mapping = yaml.safe_load(open(mapping_file, 'r'))
            for map_info in self.mapping:
                map_info['pattern'] = re.compile(map_info['old'])

    def getNewJob(self, job_name):
        for map_info in self.mapping:
            matches = map_info['pattern'].search(job_name)
            if matches:
                self.log.debug('matches: %s', matches.groupdict())
                new_name = map_info['new'].format(**matches.groupdict())
                if 'vars' not in map_info:
                    return new_name
                job_vars = map_info['vars']
                for key in job_vars.keys():
                    job_vars[key] = job_vars[key].format(**matches.groupdict())
                return {
                    new_name: {
                        'vars': job_vars
                    }
                }
        return job_name.replace('{name}-', '')


class ZuulMigrate:

    log = logging.getLogger("zuul.Migrate")

    def __init__(self, layout, job_config, outdir, mapping):
        self.layout = yaml.safe_load(open(layout, 'r'))
        self.job_config = job_config
        self.outdir = outdir
        self.mapping = JobMapping(mapping)

        self.jobs = {}

    def run(self):
        self.loadJobs()
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

    def makeNewJob(self, old_job):
        self.log.debug("makeNewJob(%s)", old_job)
        if isinstance(old_job, str):
            return self.mapping.getNewJob(old_job)

        new_list = []
        if isinstance(old_job, list):
            for job in old_job:
                new_job = self.makeNewJob(job)
                if isinstance(new_job, list):
                    new_list.extend(new_job)
                else:
                    new_list.append(self.makeNewJob(job))

        elif isinstance(old_job, dict):
            parent_name = list(old_job.keys())[0]
            parent = self.mapping.getNewJob(parent_name)

            jobs = self.makeNewJob(old_job[parent_name])
            if not isinstance(jobs, list):
                jobs = [jobs]
            for job_name in jobs:
                if isinstance(job_name, dict):
                    job = job_name
                    job_name = list(job.keys())[0]
                else:
                    job = {job_name: {}}
                # TODO(mordred) This need to only be a name
                job[job_name].setdefault('dependencies', [
                    self.mapping.getNewJob(parent_name)])
                new_list.append(job)
            new_list.append(parent)
        return new_list

    def writeProjectTemplate(self, template):
        new_template = {}
        for key, value in template.items():
            if key == 'name':
                new_template[key] = value
            else:
                new_template[key] = self.makeNewJob(value)

        return new_template

    def writeProject(self, project):
        new_project = {}
        for key, value in project.items():
            if key in ('name', 'template'):
                new_project[key] = value
            else:
                new_project[key] = self.makeNewJob(value)

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
            yaml.safe_dump(config, yamlout, default_flow_style=False)


def main():
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        'layout',
        help="The Zuul v2 layout.yaml file to read.")
    parser.add_argument(
        'job_config',
        help="Directory containing Jenkins Job Builder job definitions.")
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

    ZuulMigrate(args.layout, args.job_config, args.outdir, args.mapping).run()


if __name__ == '__main__':
    main()
