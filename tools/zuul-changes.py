#!/usr/bin/env python
# Copyright 2013 OpenStack Foundation
# Copyright 2015 Hewlett-Packard Development Company, L.P.
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

import urllib2
import json
import argparse

description = """
When provided with either the URL of a running Zuul instance or a status.json
file on disk, this script provides the commands to re-enqueue changes for the
specified tenant and pipeline.
"""

parser = argparse.ArgumentParser(description=description)
parser.add_argument('tenant', help='The Zuul tenant')
parser.add_argument('pipeline', help='The name of the Zuul pipeline')
status = parser.add_mutually_exclusive_group(required=True)
status.add_argument('--file', help='The status.json file location on disk')
status.add_argument('--url', help='The URL of a running Zuul instance')
options = parser.parse_args()

if options.url:
    data = json.loads(urllib2.urlopen('%s/status.json' % options.url).read())
else:
    with open(options.file) as f:
        data = json.load(f)

for pipeline in data['pipelines']:
    if pipeline['name'] != options.pipeline:
        continue
    for queue in pipeline['change_queues']:
        for head in queue['heads']:
            for change in head:
                if not change['live']:
                    continue
                cid, cps = change['id'].split(',')
                print(
                    "zuul enqueue --tenant %s --trigger gerrit "
                    "--pipeline %s --project %s --change %s,%s" % (
                        options.tenant,
                        options.pipeline,
                        change['project'],
                        cid, cps)
                )
