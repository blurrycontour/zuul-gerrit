#!/usr/bin/env python

# Copyright 2012 Hewlett-Packard Development Company, L.P.
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
import urllib2

from tests.base import ZuulTestCase


class TestWebapp(ZuulTestCase):

    def _cleanup(self):
        self.worker.hold_jobs_in_build = False
        self.worker.release()
        self.waitUntilSettled()

    def setUp(self):
        super(TestWebapp, self).setUp()
        self.addCleanup(self._cleanup)
        self.worker.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('CRVW', 2)
        self.fake_gerrit.addEvent(A.addApproval('APRV', 1))
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')
        B.addApproval('CRVW', 2)
        self.fake_gerrit.addEvent(B.addApproval('APRV', 1))
        self.waitUntilSettled()

    def test_webapp_status(self):
        "Test that we can filter to only certain changes in the webapp."

        port = self.webapp.server.socket.getsockname()[1]

        # testing status url
        req = urllib2.Request(
            "http://localhost:%s/status" % port)
        f = urllib2.urlopen(req)
        data = json.loads(f.read())

        self.assertIn('pipelines', data)

        # testing compat with status.json
        req = urllib2.Request(
            "http://localhost:%s/status.json" % port)
        f = urllib2.urlopen(req)
        data = json.loads(f.read())

        self.assertIn('pipelines', data)

        # do we 404 correctly
        req = urllib2.Request(
            "http://localhost:%s/status/foo" % port)
        self.assertRaises(urllib2.HTTPError, urllib2.urlopen, req)

        # can we filter by project
        req = urllib2.Request(
            "http://localhost:%s/status?project=org/project" % port)
        f = urllib2.urlopen(req)
        data = json.loads(f.read())

        self.assertEqual(1, len(data), data)
        self.assertEqual("org/project", data[0]['project'], data)

        # can we filter by change id
        req = urllib2.Request(
            "http://localhost:%s/status/change/1,1" % port)
        f = urllib2.urlopen(req)
        data = json.loads(f.read())

        self.assertEqual(1, len(data), data)
        self.assertEqual("org/project", data[0]['project'])

        req = urllib2.Request(
            "http://localhost:%s/status/change/2,1" % port)
        f = urllib2.urlopen(req)
        data = json.loads(f.read())

        self.assertEqual(1, len(data), data)
        self.assertEqual("org/project1", data[0]['project'], data)
