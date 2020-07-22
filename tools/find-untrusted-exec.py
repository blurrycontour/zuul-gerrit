# Copyright 2020 Red Hat Inc
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

import json
import sys

def examine(path):
    data = json.load(open(path))
    for playbook in data:
        if playbook['trusted']:
            continue
        for play in playbook['plays']:
            for task in play['tasks']:
                for hostname, host in task['hosts'].items():
                    if hostname != 'localhost':
                        continue
                    if host['action'] in ['command', 'shell']:
                        print("Found disallowed task:")
                        print("  Playbook: %s" % playbook['playbook'])
                        print("  Role: %s" % task.get('role', {}).get('name'))
                        print("  Task: %s" % task.get('task', {}).get('name'))

examine(sys.argv[1])
