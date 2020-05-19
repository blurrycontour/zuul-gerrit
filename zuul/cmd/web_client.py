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

import asyncio
import json
import logging
import sys
import requests
import urllib.parse
import websockets

import zuul.cmd
from zuul.lib.config import get_default


class ZuulRESTClient(object):
    """Basic client for Zuul's REST API"""
    def __init__(self, url, verify=False, auth_token=None):
        self.url = url
        if not self.url.endswith('/'):
            self.url += '/'
        self.auth_token = auth_token
        self.verify = verify
        self.base_url = urllib.parse.urljoin(self.url, 'api/')
        self.session = requests.Session()
        self.session.verify = self.verify,
        self.session.headers = dict(
            Authorization='Bearer %s' % self.auth_token)

    def _check_status(self, req):
        try:
            req.raise_for_status()
        except Exception as e:
            if req.status_code == 401:
                print('Unauthorized - your token might be invalid or expired.')
            elif req.status_code == 403:
                print('Insufficient privileges to perform the action.')
            else:
                print('Unknown error: "%e"' % e)

    def autohold(self, tenant, project, job, change, ref,
                 reason, count, node_hold_expiration):
        if not self.auth_token:
            raise Exception('Auth Token required')
        args = {"reason": reason,
                "count": count,
                "job": job,
                "change": change,
                "ref": ref,
                "node_hold_expiration": node_hold_expiration}
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/project/%s/autohold' % (tenant, project))
        req = self.session.post(url, json=args)
        self._check_status(req)
        return req.json()

    def autohold_list(self, tenant):
        if not tenant:
            raise Exception('"--tenant" argument required')
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/autohold' % tenant)
        # auth not needed here
        req = requests.get(url, verify=self.verify)
        self._check_status(req)
        resp = req.json()
        return resp

    def autohold_delete(self, id, tenant):
        if tenant is None:
            raise Exception('"--tenant" argument required')
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/autohold/%s' % (tenant, id))
        req = self.session.delete(url)
        self._check_status(req)
        # DELETE doesn't return a body, just the HTTP code
        return (req.status_code == 204)

    def autohold_info(self, id, tenant):
        if tenant is None:
            raise Exception('"--tenant" argument required')
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/autohold/%s' % (tenant, id))
        # auth not needed here
        req = requests.get(url, verify=self.verify)
        self._check_status(req)
        resp = req.json()
        return resp

    def enqueue(self, tenant, pipeline, project, trigger, change):
        if not self.auth_token:
            raise Exception('Auth Token required')
        args = {"trigger": trigger,
                "change": change,
                "pipeline": pipeline}
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/project/%s/enqueue' % (tenant, project))
        req = self.session.post(url, json=args)
        self._check_status(req)
        return req.json()

    def enqueue_ref(self, tenant, pipeline, project,
                    trigger, ref, oldrev, newrev):
        if not self.auth_token:
            raise Exception('Auth Token required')
        args = {"trigger": trigger,
                "ref": ref,
                "oldrev": oldrev,
                "newrev": newrev,
                "pipeline": pipeline}
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/project/%s/enqueue' % (tenant, project))
        req = self.session.post(url, json=args)
        self._check_status(req)
        return req.json()

    def dequeue(self, tenant, pipeline, project, change=None, ref=None):
        if not self.auth_token:
            raise Exception('Auth Token required')
        args = {"pipeline": pipeline}
        if change and not ref:
            args['change'] = change
        elif ref and not change:
            args['ref'] = ref
        else:
            raise Exception('need change OR ref')
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/project/%s/dequeue' % (tenant, project))
        req = self.session.post(url, json=args)
        self._check_status(req)
        return req.json()

    def promote(self, tenant, pipeline, change_ids):
        if not self.auth_token:
            raise Exception('Auth Token required')
        args = {'pipeline': pipeline,
                'change_ids': change_ids}
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/promote' % tenant)
        req = self.session.post(url, json=args)
        self._check_status(req)
        return req.json()

    def get_change_status(self, tenant, change):
        url = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/status/change/%s' % (tenant, change))
        req = requests.get(url, verify=self.verify)
        return req.json()

    def get_console_stream(self, tenant, change, job):
        stream_uri = urllib.parse.urljoin(
            self.base_url,
            'tenant/%s/console-stream' % tenant)
        # change protocol
        if stream_uri.startswith('http'):
            stream_uri = 'ws' + stream_uri[len('http'):]
        else:
            stream_uri = 'ws' + stream_uri
        status = self.get_change_status(tenant, change)
        if len(status) != 1:
            raise Exception('Change "%s" not found' % change)
        jobs = status[0]['jobs']
        job_info = [j for j in jobs if j['name'] == job]
        if len(job_info) != 1:
            msg = 'Job "%s" not found for change %s\n' % (job, change)
            msg += 'Possible jobs are:\n'
            for j in jobs:
                msg += '\t%s\n' % j['name']
            raise Exception(msg)
        job_info = job_info[0]
        if job_info['result'] is not None:
            print(
                'Job ended in status "%s", '
                'report URL is %s' % (job_info['result'],
                                      job_info['report_url']))
            return
        if not job_info['queued']:
            raise Exception('Job not queued yet')
        uuid = job_info['uuid']
        payload = {'uuid': uuid, 'logfile': 'console.log'}

        async def logstream():
            async with websockets.connect(stream_uri) as w:
                await w.send(json.dumps(payload))
                async for message in w:
                    print("{}".format(message))

        asyncio.get_event_loop().run_until_complete(logstream())


class WebClient(zuul.cmd.ZuulClientApp):
    app_name = 'zuul-web-client'
    app_description = 'Zuul Web CLI client.'
    log = logging.getLogger("zuul.WebClient")

    def createParser(self):
        parser = super(WebClient, self).createParser()
        parser.add_argument('--auth-token', dest='auth_token',
                            required=False,
                            default=None,
                            help='Authentication Token, required by '
                                 'admin commands')
        parser.add_argument('--zuul-url', dest='zuul_url',
                            required=False,
                            default=None,
                            help='Zuul base URL, needed if using the '
                                 'client without a configuration file')
        parser.add_argument('--insecure', dest='insecure_ssl',
                            required=False,
                            action='store_false',
                            help='Do not verify SSL connection to Zuul '
                                 '(Defaults to False)')
        return parser

    def createCommandParsers(self, parser):
        subparsers = super(WebClient, self).createCommandParsers(parser)
        self.add_console_stream_sbuparser(subparsers)
        return subparsers

    def main(self):
        self.parseArguments()
        if not self.args.zuul_url:
            self.readConfig()
        self.setup_logging()

        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)

    def get_client(self):
        if self.args.zuul_url:
            self.log.debug(
                'Using Zuul URL provided as argument to instantiate client')
            client = ZuulRESTClient(self.args.zuul_url,
                                    self.args.insecure_ssl,
                                    self.args.auth_token)
            return client
        conf_sections = self.config.sections()
        if 'webclient' in conf_sections:
            self.log.debug(
                'Using webclient section found in '
                'config to instantiate client')
            server = get_default(self.config, 'webclient', 'url', None)
            verify = get_default(self.config, 'webclient', 'verify_ssl',
                                 self.args.insecure_ssl)
            client = ZuulRESTClient(server, verify,
                                    self.args.auth_token)
        else:
            print('Unable to find a way to connect to Zuul, provide the '
                  '"--zuul-url" argument or add a "webclient" section to '
                  'your configuration file')
            sys.exit(1)
        if server is None:
            print('Missing "url" configuration value')
            sys.exit(1)
        return client

    def add_console_stream_subparser(self, subparsers):
        cmd_cstream = subparsers.add_parser('console-stream',
                                            help='Stream the console log '
                                                 'for the job of a given '
                                                 'change')
        cmd_cstream.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_cstream.add_argument('--job', help='job name',
                                 required=True)
        cmd_cstream.add_argument('--change', help='change id',
                                 required=True)
        cmd_cstream.set_defaults(func=self.console_stream)

    def console_stream(self):
        client = self.get_client()
        client.get_console_stream(self.args.tenant,
                                  self.args.change,
                                  self.args.job)


def main():
    WebClient().main()
