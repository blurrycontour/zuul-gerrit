# Copyright 2018 Red Hat, Inc.
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


from tests.base import ZuulTestCase
from zuul.lib.config import get_default


class TestDefualtConfigValue(ZuulTestCase):
    config_file = 'zuul.conf'

    def setup_config(self):
        super(TestDefualtConfigValue, self).setup_config()

    def test_default_config_value(self):
        default_value = get_default(self.config,
                                    'web',
                                    'static_cache_expiry')
        self.assertEqual(1200, default_value)
