# Copyright 2016 GoodData
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

import os

from tests.base import ZuulTestCase

LAYOUT_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestLayout(ZuulTestCase):
    def test_template_cartesian(self):
        """Tests that specifying lists for multiple keys create jobs according
        to cartesian product of the lists"""
        layout = self.get_template('layout-template-cartesian.yaml')
        job_names = layout.jobs.keys()
        self.assertIn('master-unit', job_names)
        self.assertIn('master-regression', job_names)
        self.assertIn('stable-unit', job_names)
        self.assertIn('stable-regression', job_names)

    def get_template(self, name):
        """Returns parsed template"""
        layout_path = os.path.join(LAYOUT_DIR, name)
        return self.sched.testConfig(layout_path, self.connections)
