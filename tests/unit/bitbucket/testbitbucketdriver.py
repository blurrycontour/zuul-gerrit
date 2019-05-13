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

from zuul.driver.bitbucket import BitbucketDriver
from zuul.driver.bitbucket.bitbucketsource import BitbucketSource
from zuul.driver.bitbucket.bitbucketconnection import BitbucketConnection
from tests.base import BaseTestCase


class TestBitbucketDriver(BaseTestCase):
    def test_getRequireSchema(self):
        drv = BitbucketDriver()
        self.assertEqual({}, drv.getRequireSchema())

    def test_getRejectSchema(self):
        drv = BitbucketDriver()
        self.assertEqual({}, drv.getRejectSchema())

    def test_getSource(self):
        drv = BitbucketDriver()
        cfg = {'baseurl': 'https://bitbucket.glumfun.test',
               'cloneurl': 'ssh://git@bitbucket.glumfun'
               '.test',
               'user': 'mark',
               'password': 'foobar'}
        self.assertIsInstance(drv.getSource(drv.getConnection('foo', cfg)),
                              BitbucketSource)

    def test_getConnection(self):
        drv = BitbucketDriver()
        cfg = {'baseurl': 'https://bitbucket.glumfun.test',
               'cloneurl': 'ssh://git@bitbucket.glumfun'
               '.test',
               'user': 'mark',
               'password': 'foobar'}
        self.assertIsInstance(drv.getConnection('foo', cfg),
                              BitbucketConnection)
