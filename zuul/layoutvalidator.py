# Copyright 2013 OpenStack Foundation
# Copyright 2013 Antoine "hashar" Musso
# Copyright 2013 Wikimedia Foundation Inc.
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

import voluptuous as v


# Several forms accept either a single item or a list, this makes
# specifying that in the schema easy (and explicit).
def toList(x):
    return v.Any([x], x)


class LayoutSchema(object):
    include = {'python-file': str}
    includes = [include]

    manager = v.Any('IndependentPipelineManager',
                    'DependentPipelineManager')
    variable_dict = v.Schema({}, extra=True)

    trigger = {v.Required('event'): toList(v.Any('patchset-created',
                                                 'change-abandoned',
                                                 'change-restored',
                                                 'change-merged',
                                                 'comment-added',
                                                 'ref-updated')),
               'comment_filter': toList(str),
               'email_filter': toList(str),
               'branch': toList(str),
               'ref': toList(str),
               'approval': toList(variable_dict),
               }

    pipeline = {v.Required('name'): str,
                v.Required('manager'): manager,
                'description': str,
                'success-message': str,
                'failure-message': str,
                'dequeue-on-new-patchset': bool,
                'trigger': toList(trigger),
                'success': variable_dict,
                'failure': variable_dict,
                'start': variable_dict,
                }
    pipelines = [pipeline]

    project_template = {
        v.Required('name'): str,
        v.Required('template'): dict,
    }
    project_templates = [project_template]

    job = {v.Required('name'): str,
           'failure-message': str,
           'success-message': str,
           'failure-pattern': str,
           'success-pattern': str,
           'hold-following-changes': bool,
           'voting': bool,
           'parameter-function': str,
           'branch': toList(str),
           }
    jobs = [job]

    job_name = v.Schema(v.Match("^\S+$"))

    def validateJob(self, value, path=[]):
        if isinstance(value, list):
            for (i, v) in enumerate(value):
                self.validateJob(v, path + [i])
        elif isinstance(value, dict):
            for k, v in value.items():
                self.validateJob(v, path + [k])
        else:
            self.job_name.validate(path, self.job_name.schema, value)

    def getSchema(self, data):
        pipelines = data.get('pipelines')
        if not pipelines:
            pipelines = []
        pipelines = [p['name'] for p in pipelines if 'name' in p]

        # Whenever a project use a template, it better have to exist
        template_names = [t['name'] for t in data.get('project-templates')
                          if 'name' in t]
        template_call = v.Schema({
            v.Required('name'): v.Any(*template_names),
            }, extra=True )
        project = {'name': str,
                   'merge-mode': v.Any('cherry-pick'),
                   'template': [template_call],
                   }
        # And project should refers to existing pipelines
        for p in pipelines:
            project[p] = self.validateJob
        projects = [project]

        # Sub schema to validate a project template has existing
        # pipelines and jobs.
        project_template = { 'name': str,
                             'template': {},
                           }
        for p in pipelines:
            project_template['template'][p] = self.validateJob
        project_templates = [project_template]

        # Gather our sub schemas
        schema = v.Schema({'includes': self.includes,
                           v.Required('pipelines'): self.pipelines,
                           'jobs': self.jobs,
                           'project-templates': project_templates,
                           v.Required('projects'): projects,
                           })
        return schema


class LayoutValidator(object):
    def checkDuplicateNames(self, data, path):
        items = []
        for i, item in enumerate(data):
            if item['name'] in items:
                raise v.Invalid("Duplicate name: %s" % item['name'],
                                path + [i])
            items.append(item['name'])

    def validate(self, data):
        schema = LayoutSchema().getSchema(data)
        schema(data)
        self.checkDuplicateNames(data['pipelines'], ['pipelines'])
        if 'jobs' in data:
            self.checkDuplicateNames(data['jobs'], ['jobs'])
        self.checkDuplicateNames(data['projects'], ['projects'])
        if 'project-templates' in data:
            self.checkDuplicateNames(data['project-templates'], ['project-templates'])
