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

