#!/usr/bin/env python3
#
# Copyright 2020 BMW Group
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

from ansible.module_utils.basic import AnsibleModule


def check_shards(zuul_source):
    test_dir = os.path.join(zuul_source, 'tests/unit')
    files = os.listdir(test_dir)

    # Generate list of test modules in folder tests/unit
    test_files = [f for f in files
                  if f != '__init__.py'
                  if f.endswith('.py')]
    test_modules = sorted(
        ['tests.unit.%s' % os.path.splitext(f)[0] for f in test_files])

    shard_files = [os.path.join(test_dir, f) for f in files
                   if f.startswith('shard')]
    sharded_test_modules = []
    for file in shard_files:
        with open(file) as f:
            sharded_test_modules.extend([
                f.strip() for f in f.readlines()
                if not f.startswith('#')
                if f.strip()
            ])
    sharded_test_modules = sorted(sharded_test_modules)

    return test_modules == sharded_test_modules


def ansible_main():
    module = AnsibleModule(
        argument_spec=dict(
            zuul_source=dict(required=True, type='path'),
        )
    )

    if check_shards(module.params.get('zuul_source')):
        module.exit_json(changed=False)
    else:
        module.fail_json(msg="Sharded list of test modules is not complete.")


if __name__ == '__main__':
    ansible_main()
