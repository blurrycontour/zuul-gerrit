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


def zuul_legacy_vars(zuul):
    # omitted:
    # ZUUL_URL
    # ZUUL_REF
    # ZUUL_COMMIT

    short_name = zuul['project']['name'].split('/')[-1]
    params = dict(ZUUL_UUID=zuul['build'],
                  ZUUL_PROJECT=zuul['project']['name'],
                  ZUUL_SHORT_PROJECT_NAME=short_name,
                  ZUUL_PIPELINE=zuul['pipeline'],
                  ZUUL_VOTING=zuul['voting'],
                  WORKSPACE='/home/zuul/workspace')
    if 'timeout' in zuul and zuul['timeout'] is not None:
        params['BUILD_TIMEOUT'] = str(int(zuul['timeout']) * 1000)
    if 'branch' in zuul:
        params['ZUUL_BRANCH'] = zuul['branch']

    if 'change' in zuul:
        changes_str = '^'.join(
            ['%s:%s:refs/changes/%s/%s/%s' % (
                i['project']['name'],
                i['branch'],
                str(i['change'])[:-2:],
                i['change'],
                i['patchset'])
             for i in zuul['items']])
        params['ZUUL_CHANGES'] = changes_str

        change_ids = ' '.join(['%s,%s' % (i['change'], i['patchset'])
                               for i in zuul['items']])
        params['ZUUL_CHANGE_IDS'] = change_ids
        params['ZUUL_CHANGE'] = str(zuul['change'])
        params['ZUUL_PATCHSET'] = str(zuul['patchset'])

    if 'newrev' in zuul or 'oldrev' in zuul:
        params['ZUUL_REFNAME'] = zuul['ref']
        params['ZUUL_OLDREV'] = zuul.get('oldrev', '0' * 40)
        params['ZUUL_NEWREV'] = zuul.get('newrev', '0' * 40)

    params['TOX_TESTENV_PASSENV'] = ' '.join(params.keys())
    return params


def zuul_projects_by_name(zuul):
    ret = {}
    for project in zuul['projects']:
        ret[project['name']] = project
    return name


def zuul_projects_by_canonical_name(zuul):
    ret = {}
    for project in zuul['projects']:
        ret[project['canonical_name']] = project
    return name


def zuul_projects_by_short_name(zuul):
    ret = {}
    for project in zuul['projects']:
        ret[project['short_name']] = project
    return name


def zuul_project(zuul, name):
    for func in (zuul_projects_by_short_name, zuul_projects_by_name,
                 zuul_projects_by_canonical_name):
        projects = func(zuul)
        if name in projects:
            return projects[name]
    return None


def zuul_required_projects(zuul):
    return [project for project in zuul['projects'] if project['required']]


class FilterModule(object):

    def filters(self):
        return {
            'zuul_legacy_vars': zuul_legacy_vars,
            'zuul_project': zuul_project,
            'zuul_projects_by_canonical_name': zuul_projects_by_canonical_name,
            'zuul_projects_by_name': zuul_projects_by_name,
            'zuul_projects_by_short_name': zuul_projects_by_short_name,
            'zuul_required_projects': zuul_required_projects,
        }
