# Copyright 2013 OpenStack Foundation
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

import voluptuous
import yaml

# Several forms accept either a single item or a list, this makes
# specifying that in the schema easy (and explicit).
def toList(x):
    return voluptuous.any([x], x)

class LayoutSchema(object):
    include = {'python-file': str}
    includes = [include]

    manager = voluptuous.any('IndependentPipelineManager',
                             'DependentPipelineManager')
    variable_dict = voluptuous.Schema({}, extra=True)
    trigger = {'event': toList(voluptuous.any('patchset-created',
                                              'change-abandoned',
                                              'change-restored',
                                              'change-merged',
                                              'comment-added',
                                              'ref-updated')),
               'comment_filter': voluptuous.optional(toList(str)),
               'email_filter': voluptuous.optional(toList(str)),
               'branch': voluptuous.optional(toList(str)),
               'ref': voluptuous.optional(toList(str)),
               'approval': voluptuous.optional(toList(variable_dict)),
               }
    pipeline = {
        'name': str,
        'description': str,
        'manager': manager,
        'trigger': toList(trigger),
        'success': voluptuous.optional(variable_dict),
        'failure': voluptuous.optional(variable_dict),
        'start': voluptuous.optional(variable_dict),
        }
    pipelines = [pipeline]

    job = {
        'name': str,
        'failure-message': str,
        'success-message': str,
        'failure-pattern': str,
        'success-pattern': str,
        'hold-following-changes': bool,
        'voting': bool,
        'parameter-function': str,  # TODO: validate the function is importable
        }
    jobs = [job]

    project = voluptuous.Schema({
            'name': str,
            }, extra=True)
    projects = [project]

    schema = voluptuous.Schema({'includes': includes,
                                'pipelines': pipelines,
                                'jobs': jobs,
                                'projects': projects,
                                })

class LayoutValidator(object):
    def validate(self, data):
        LayoutSchema.schema(data)

