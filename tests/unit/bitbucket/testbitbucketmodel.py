# Copyright 2019 Smaato, Inc.
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

from zuul.driver.bitbucket.bitbucketmodel import PullRequest
from tests.base import BaseTestCase


class TestBitbucketModel(BaseTestCase):
    def test_isUpdateOf(self):
        pr_a = PullRequest('aaa')
        pr_a.id = 101
        pr_a.patchset = ['foo', 'bar']
        pr_a.updatedDate = 1060

        pr_b = PullRequest('aaa')
        pr_b.id = 101
        pr_b.patchset = ['foo', 'xyz']
        pr_b.updatedDate = 2120

        pr_c = PullRequest('ccc')
        pr_c.id = 101
        pr_c.patchset = ['foo', 'bar']
        pr_c.updatedDate = 1060

        self.assertFalse(pr_a.isUpdateOf(pr_b))
        self.assertTrue(pr_b.isUpdateOf(pr_a))
        self.assertFalse(pr_c.isUpdateOf(pr_a))
