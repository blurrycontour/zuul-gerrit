# Copyright 2019 Red Hat, Inc.
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


def append_playbook(playbook, output_path):
    first_time = not os.path.exists(output_path)

    if first_time:
        with open(output_path, 'w') as outfile:
            outfile.write('[\n\n]\n')

    with open(output_path, 'w') as outfile:
        file_len = outfile.seek(0, os.SEEK_END)
        # Remove three bytes to eat the trailing newline written by the
        # json.dump. This puts the ',' on the end of lines.
        outfile.seek(file_len - 3)
        if not first_time:
            outfile.write(',\n')
        json.dump(playbook, outfile,
                  indent=4, sort_keys=True, separators=(',', ': '))
        outfile.write('\n]\n')
