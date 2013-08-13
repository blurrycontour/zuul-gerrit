#!/usr/bin/env python

# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

import gear
import json


def select_debian_node(item, params):
    params['ZUUL_NODE'] = 'debian'


def start_function(scheduler, build):
    params = {'phase': 'start',
              'worker': build.result_data['worker']}

    gearman_job = gear.Job('other:start-function', json.dumps(params))
    x = scheduler.launcher.gearman.submitJob(gearman_job)


def complete_function(scheduler, build):
    params = {'phase': 'complete',
              'worker': build.result_data['worker']}

    gearman_job = gear.Job('other:complete-function', json.dumps(params))
    scheduler.launcher.gearman.submitJob(gearman_job)
