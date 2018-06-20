#!/usr/bin/env python

# Copyright 2014 Hewlett-Packard Development Company, L.P.
# Copyright 2014 Rackspace Australia
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
import os
import urllib.parse
import socket
import time
import jwt

import requests

import zuul.web
import zuul.rpcclient

from tests.base import ZuulTestCase, ZuulDBTestCase, FIXTURE_DIR
from tests.base import ZuulWebFixture


class FakeConfig(object):

    def __init__(self, config):
        self.config = config or {}

    def has_option(self, section, option):
        return option in self.config.get(section, {})

    def get(self, section, option):
        return self.config.get(section, {}).get(option)


class BaseTestWeb(ZuulTestCase):
    tenant_config_file = 'config/single-tenant/main.yaml'
    config_ini_data = {}

    def setUp(self):
        super(BaseTestWeb, self).setUp()

        self.zuul_ini_config = FakeConfig(self.config_ini_data)
        enable_admin_endpoints = self.zuul_ini_config.get(
            'web', 'enable_admin_endpoints')
        # Start the web server
        self.web = self.useFixture(
            ZuulWebFixture(
                self.gearman_server.port,
                self.config,
                info=zuul.model.WebInfo.fromConfig(self.zuul_ini_config),
                enable_admin_endpoints=enable_admin_endpoints,
                JWTsecret=self.zuul_ini_config.get('web', 'JWTsecret')))

        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        B = self.fake_gerrit.addFakeChange('org/project1', 'master', 'B')
        B.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(B.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.host = 'localhost'
        self.port = self.web.port
        # Wait until web server is started
        while True:
            try:
                with socket.create_connection((self.host, self.port)):
                    break
            except ConnectionRefusedError:
                pass
        self.base_url = "http://{host}:{port}".format(
            host=self.host, port=self.port)

    def get_url(self, url, *args, **kwargs):
        return requests.get(
            urllib.parse.urljoin(self.base_url, url), *args, **kwargs)

    def post_url(self, url, *args, **kwargs):
        return requests.post(
            urllib.parse.urljoin(self.base_url, url), *args, **kwargs)

    def tearDown(self):
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()
        super(BaseTestWeb, self).tearDown()


class TestWeb(BaseTestWeb):

    def test_web_status(self):
        "Test that we can retrieve JSON status info"
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.executor_server.release('project-merge')
        self.waitUntilSettled()

        resp = self.get_url("api/tenant/tenant-one/status")
        self.assertIn('Content-Length', resp.headers)
        self.assertIn('Content-Type', resp.headers)
        self.assertEqual(
            'application/json; charset=utf-8', resp.headers['Content-Type'])
        self.assertIn('Access-Control-Allow-Origin', resp.headers)
        self.assertIn('Cache-Control', resp.headers)
        self.assertIn('Last-Modified', resp.headers)

        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        data = resp.json()
        status_jobs = []
        for p in data['pipelines']:
            for q in p['change_queues']:
                if p['name'] in ['gate', 'conflict']:
                    self.assertEqual(q['window'], 20)
                else:
                    self.assertEqual(q['window'], 0)
                for head in q['heads']:
                    for change in head:
                        self.assertTrue(change['active'])
                        self.assertIn(change['id'], ('1,1', '2,1', '3,1'))
                        for job in change['jobs']:
                            status_jobs.append(job)
        self.assertEqual('project-merge', status_jobs[0]['name'])
        # TODO(mordred) pull uuids from self.builds
        self.assertEqual(
            'stream.html?uuid={uuid}&logfile=console.log'.format(
                uuid=status_jobs[0]['uuid']),
            status_jobs[0]['url'])
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[0]['uuid']),
            status_jobs[0]['finger_url'])
        # TOOD(mordred) configure a success-url on the base job
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[0]['uuid']),
            status_jobs[0]['report_url'])
        self.assertEqual('project-test1', status_jobs[1]['name'])
        self.assertEqual(
            'stream.html?uuid={uuid}&logfile=console.log'.format(
                uuid=status_jobs[1]['uuid']),
            status_jobs[1]['url'])
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[1]['uuid']),
            status_jobs[1]['finger_url'])
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[1]['uuid']),
            status_jobs[1]['report_url'])

        self.assertEqual('project-test2', status_jobs[2]['name'])
        self.assertEqual(
            'stream.html?uuid={uuid}&logfile=console.log'.format(
                uuid=status_jobs[2]['uuid']),
            status_jobs[2]['url'])
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[2]['uuid']),
            status_jobs[2]['finger_url'])
        self.assertEqual(
            'finger://{hostname}/{uuid}'.format(
                hostname=self.executor_server.hostname,
                uuid=status_jobs[2]['uuid']),
            status_jobs[2]['report_url'])

        # check job dependencies
        self.assertIsNotNone(status_jobs[0]['dependencies'])
        self.assertIsNotNone(status_jobs[1]['dependencies'])
        self.assertIsNotNone(status_jobs[2]['dependencies'])
        self.assertEqual(len(status_jobs[0]['dependencies']), 0)
        self.assertEqual(len(status_jobs[1]['dependencies']), 1)
        self.assertEqual(len(status_jobs[2]['dependencies']), 1)
        self.assertIn('project-merge', status_jobs[1]['dependencies'])
        self.assertIn('project-merge', status_jobs[2]['dependencies'])

    def test_web_tenants(self):
        "Test that we can retrieve JSON status info"
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        self.fake_gerrit.addEvent(A.addApproval('Approved', 1))
        self.waitUntilSettled()

        self.executor_server.release('project-merge')
        self.waitUntilSettled()

        resp = self.get_url("api/tenants")
        self.assertIn('Content-Length', resp.headers)
        self.assertIn('Content-Type', resp.headers)
        self.assertEqual(
            'application/json; charset=utf-8', resp.headers['Content-Type'])
        # self.assertIn('Access-Control-Allow-Origin', resp.headers)
        # self.assertIn('Cache-Control', resp.headers)
        # self.assertIn('Last-Modified', resp.headers)
        data = resp.json()

        self.assertEqual('tenant-one', data[0]['name'])
        self.assertEqual(3, data[0]['projects'])
        self.assertEqual(3, data[0]['queue'])

        # release jobs and check if the queue size is 0
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        data = self.get_url("api/tenants").json()
        self.assertEqual('tenant-one', data[0]['name'])
        self.assertEqual(3, data[0]['projects'])
        self.assertEqual(0, data[0]['queue'])

        # test that non-live items are not counted
        self.executor_server.hold_jobs_in_build = True
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        B.setDependsOn(A, 1)
        self.fake_gerrit.addEvent(B.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        req = urllib.request.Request(
            "http://127.0.0.1:%s/api/tenants" % self.port)
        f = urllib.request.urlopen(req)
        data = f.read().decode('utf8')
        data = json.loads(data)

        self.assertEqual('tenant-one', data[0]['name'])
        self.assertEqual(3, data[0]['projects'])
        self.assertEqual(1, data[0]['queue'])

    def test_web_bad_url(self):
        # do we 404 correctly
        resp = self.get_url("status/foo")
        self.assertEqual(404, resp.status_code)

    def test_web_find_change(self):
        # can we filter by change id
        data = self.get_url("api/tenant/tenant-one/status/change/1,1").json()

        self.assertEqual(1, len(data), data)
        self.assertEqual("org/project", data[0]['project'])

        data = self.get_url("api/tenant/tenant-one/status/change/2,1").json()

        self.assertEqual(1, len(data), data)
        self.assertEqual("org/project1", data[0]['project'], data)

    def test_web_keys(self):
        with open(os.path.join(FIXTURE_DIR, 'public.pem'), 'rb') as f:
            public_pem = f.read()

        resp = self.get_url("api/tenant/tenant-one/key/org/project.pub")
        self.assertEqual(resp.content, public_pem)
        self.assertIn('text/plain', resp.headers.get('Content-Type'))

    def test_web_404_on_unknown_tenant(self):
        resp = self.get_url("api/tenant/non-tenant/status")
        self.assertEqual(404, resp.status_code)

    def test_admin_routes_403_by_default(self):
        resp = self.get_url("api/tenant/tenant-one/autohold")
        self.assertEqual(403, resp.status_code)
        resp = self.post_url("api/tenant/tenant-one/autohold",
                             json={'project': 'org/project',
                                   'job': 'project-test1',
                                   'count': 1,
                                   'reason': 'because',
                                   'node_hold_expiration': 36000})
        self.assertEqual(403, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            json={'trigger': 'gerrit',
                  'change': '2,1',
                  'pipeline': 'check'})
        self.assertEqual(403, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            json={'trigger': 'gerrit',
                  'ref': 'abcd',
                  'newrev': 'aaaa',
                  'oldrev': 'bbbb',
                  'pipeline': 'check'})
        self.assertEqual(403, resp.status_code)


class TestInfo(BaseTestWeb):

    def setUp(self):
        super(TestInfo, self).setUp()
        web_config = self.config_ini_data.get('web', {})
        self.websocket_url = web_config.get('websocket_url')
        self.stats_url = web_config.get('stats_url')
        statsd_config = self.config_ini_data.get('statsd', {})
        self.stats_prefix = statsd_config.get('prefix')

    def test_info(self):
        info = self.get_url("api/info").json()
        self.assertEqual(
            info, {
                "info": {
                    "admin_endpoints_enabled": False,
                    "capabilities": {
                        "job_history": False
                    },
                    "stats": {
                        "url": self.stats_url,
                        "prefix": self.stats_prefix,
                        "type": "graphite",
                    },
                    "websocket_url": self.websocket_url,
                }
            })

    def test_tenant_info(self):
        info = self.get_url("api/tenant/tenant-one/info").json()
        self.assertEqual(
            info, {
                "info": {
                    "admin_endpoints_enabled": False,
                    "tenant": "tenant-one",
                    "capabilities": {
                        "job_history": False
                    },
                    "stats": {
                        "url": self.stats_url,
                        "prefix": self.stats_prefix,
                        "type": "graphite",
                    },
                    "websocket_url": self.websocket_url,
                }
            })


class TestWebSocketInfo(TestInfo):

    config_ini_data = {
        'web': {
            'websocket_url': 'wss://ws.example.com'
        }
    }


class TestGraphiteUrl(TestInfo):

    config_ini_data = {
        'statsd': {
            'prefix': 'example'
        },
        'web': {
            'stats_url': 'https://graphite.example.com',
        }
    }


class TestBuildInfo(ZuulDBTestCase, BaseTestWeb):
    config_file = 'zuul-sql-driver.conf'
    tenant_config_file = 'config/sql-driver/main.yaml'

    def test_web_list_builds(self):
        # Generate some build records in the db.
        self.executor_server.hold_jobs_in_build = False
        self.executor_server.release()
        self.waitUntilSettled()

        builds = self.get_url("api/tenant/tenant-one/builds").json()
        self.assertEqual(len(builds), 6)


class TestTenantScopedWebApi(BaseTestWeb):
    config_ini_data = {
        'web': {
            'enable_admin_endpoints': True,
            'JWTsecret': 'NoDanaOnlyZuul',
        }
    }

    def test_admin_routes_no_token(self):
        resp = self.get_url("api/tenant/tenant-one/autohold")
        self.assertEqual(401, resp.status_code)
        resp = self.post_url("api/tenant/tenant-one/autohold",
                             json={'project': 'org/project',
                                   'job': 'project-test1',
                                   'count': 1,
                                   'reason': 'because',
                                   'node_hold_expiration': 36000})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            json={'trigger': 'gerrit',
                  'change': '2,1',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            json={'trigger': 'gerrit',
                  'ref': 'abcd',
                  'newrev': 'aaaa',
                  'oldrev': 'bbbb',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)

    def test_bad_key_JWT_token(self):
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='OnlyZuulNoDana',
                           algorithm='HS256').decode('utf-8')
        resp = self.get_url(
            "api/tenant/tenant-one/autohold",
            headers={'Authorization': 'Bearer %s' % token})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url("api/tenant/tenant-one/autohold",
                             headers={'Authorization': 'Bearer %s' % token},
                             json={'project': 'org/project',
                                   'job': 'project-test1',
                                   'count': 1,
                                   'reason': 'because',
                                   'node_hold_expiration': 36000})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'change': '2,1',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'ref': 'abcd',
                  'newrev': 'aaaa',
                  'oldrev': 'bbbb',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)

    def test_expired_JWT_token(self):
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() - 3600}
        token = jwt.encode(authz, key='OnlyZuulNoDana',
                           algorithm='HS256').decode('utf-8')
        resp = self.get_url(
            "api/tenant/tenant-one/autohold",
            headers={'Authorization': 'Bearer %s' % token})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url("api/tenant/tenant-one/autohold",
                             headers={'Authorization': 'Bearer %s' % token},
                             json={'project': 'org/project',
                                   'job': 'project-test1',
                                   'count': 1,
                                   'reason': 'because',
                                   'node_hold_expiration': 36000})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'change': '2,1',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'ref': 'abcd',
                  'newrev': 'aaaa',
                  'oldrev': 'bbbb',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)

    def test_valid_JWT_bad_tenants(self):
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-six', 'tenant-ten'],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        resp = self.get_url(
            "api/tenant/tenant-one/autohold",
            headers={'Authorization': 'Bearer %s' % token})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url("api/tenant/tenant-one/autohold",
                             headers={'Authorization': 'Bearer %s' % token},
                             json={'project': 'org/project',
                                   'job': 'project-test1',
                                   'count': 1,
                                   'reason': 'because',
                                   'node_hold_expiration': 36000})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'change': '2,1',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)
        resp = self.post_url(
            "api/tenant/tenant-one/project/org/project/enqueue",
            headers={'Authorization': 'Bearer %s' % token},
            json={'trigger': 'gerrit',
                  'ref': 'abcd',
                  'newrev': 'aaaa',
                  'oldrev': 'bbbb',
                  'pipeline': 'check'})
        self.assertEqual(401, resp.status_code)

    def test_autohold(self):
        """Test that autohold can be set through the admin web interface"""
        args = {"reason": "some reason",
                "count": 1,
                'job': 'project-test2',
                'project': 'org/project',
                'change': None,
                'ref': None,
                'node_hold_expiration': None}
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        req = self.post_url(
            'api/tenant/tenant-one/autohold',
            headers={'Authorization': 'Bearer %s' % token},
            json=args)
        self.assertEqual(200, req.status_code, req.text)
        data = req.json()
        self.assertEqual(True, data)

        # Check result in rpc client
        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        autohold_requests = client.autohold_list()
        self.assertNotEqual({}, autohold_requests)
        self.assertEqual(1, len(autohold_requests.keys()))
        key = list(autohold_requests.keys())[0]
        tenant, project, job, ref_filter = key.split(',')
        self.assertEqual('tenant-one', tenant)
        self.assertIn('org/project', project)
        self.assertEqual('project-test2', job)
        self.assertEqual(".*", ref_filter)
        # Note: the value is converted from set to list by json.
        self.assertEqual([1, "some reason", None], autohold_requests[key],
                         autohold_requests[key])

    def test_autohold_list(self):
        """test listing autoholds through zuul-web"""
        client = zuul.rpcclient.RPCClient('127.0.0.1',
                                          self.gearman_server.port)
        self.addCleanup(client.shutdown)
        r = client.autohold('tenant-one', 'org/project', 'project-test2',
                            "", "", "reason text", 1)
        self.assertTrue(r)
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        resp = self.get_url(
            "api/tenant/tenant-one/autohold",
            headers={'Authorization': 'Bearer %s' % token})
        self.assertEqual(200, resp.status_code, resp.text)
        autohold_requests = resp.json()

        self.assertNotEqual([], autohold_requests)
        self.assertEqual(1, len(autohold_requests))
        # The single dict key should be a CSV string value
        ah_request = autohold_requests[0]

        self.assertEqual('tenant-one', ah_request['tenant'])
        self.assertIn('org/project', ah_request['project'])
        self.assertEqual('project-test2', ah_request['job'])
        self.assertEqual(".*", ah_request['ref_filter'])
        self.assertEqual(1, ah_request['count'])
        self.assertEqual("reason text", ah_request['reason'])

    def test_enqueue(self):
        """Test that the admin web interface can enqueue a change"""
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.addApproval('Code-Review', 2)
        A.addApproval('Approved', 1)

        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        path = "api/tenant/%(tenant)s/project/%(project)s/enqueue"
        enqueue_args = {'tenant': 'tenant-one',
                        'project': 'org/project', }
        change = {'trigger': 'gerrit',
                  'change': '1,1',
                  'pipeline': 'gate', }
        req = self.post_url(path % enqueue_args,
                            headers={'Authorization': 'Bearer %s' % token},
                            json=change)
        # The JSON returned is the same as the client's output
        self.assertEqual(200, req.status_code, req.text)
        data = req.json()
        self.assertEqual(True, data)
        self.waitUntilSettled()

    def test_enqueue_ref(self):
        """Test that the admin web interface can enqueue a ref"""
        p = "review.example.com/org/project"
        upstream = self.getUpstreamRepos([p])
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        A.setMerged()
        A_commit = str(upstream[p].commit('master'))
        self.log.debug("A commit: %s" % A_commit)

        path = "api/tenant/%(tenant)s/project/%(project)s/enqueue"
        enqueue_args = {'tenant': 'tenant-one',
                        'project': 'org/project', }
        ref = {'trigger': 'gerrit',
               'ref': 'master',
               'oldrev': '90f173846e3af9154517b88543ffbd1691f31366',
               'newrev': A_commit,
               'pipeline': 'post', }
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        req = self.post_url(path % enqueue_args,
                            headers={'Authorization': 'Bearer %s' % token},
                            json=ref)
        self.assertEqual(200, req.status_code, req.text)
        # The JSON returned is the same as the client's output
        data = req.json()
        self.assertEqual(True, data)
        self.waitUntilSettled()

    def test_JWT_as_query_arg(self):
        """Test that the JWToken can get passed as the 'jwt' query argument"""
        args = {"reason": "some reason",
                "count": 1,
                'job': 'project-test2',
                'project': 'org/project',
                'change': None,
                'ref': None,
                'node_hold_expiration': None}
        authz = {'iss': 'me', 'zuul.tenants': ['tenant-one', ],
                 'exp': time.time() + 3600}
        token = jwt.encode(authz, key='NoDanaOnlyZuul',
                           algorithm='HS256').decode('utf-8')
        req = self.post_url(
            'api/tenant/tenant-one/autohold?jwt=%s' % token,
            json=args)
        self.assertEqual(200, req.status_code, req.text)
        data = req.json()
        self.assertEqual(True, data)
