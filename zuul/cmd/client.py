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

import argparse
import babel.dates
import datetime
import jwt
import logging
import prettytable
import re
import sys
import time
import textwrap

from zuulclient.api import ZuulRESTClient
from zuulclient.common.client import CLI
import zuul.lib.connections

import zuul.rpcclient
import zuul.cmd
from zuul.lib.config import get_default


class Client(CLI):
    app_name = 'zuul'
    app_description = 'Zuul CLI client.'
    log = logging.getLogger("zuul.Client")

    def createParser(self):
        parser = super(Client, self).createParser()
        parser.add_argument('--auth-token', dest='auth_token',
                            required=False,
                            default=None,
                            help='[DEPRECATED] Authentication Token, needed '
                                 'if using the REST API')
        parser.add_argument('--zuul-url', dest='zuul_url',
                            required=False,
                            default=None,
                            help='[DEPRECATED] Zuul API URL, needed if using '
                                 'the REST API without a configuration file')
        parser.add_argument('--insecure', dest='insecure_ssl',
                            required=False,
                            action='store_false',
                            help='[DEPRECATED] Do not verify SSL connection '
                                 'to Zuul, when using the REST API '
                                 '(Defaults to False)')
        self.createCommandParsers(parser)
        return parser

    def createCommandParsers(self, parser):
        subparsers = super(Client, self).createCommandParsers(parser)
        self.add_show_subparser(subparsers)
        self.add_conf_check_subparser(subparsers)
        self.add_create_auth_token_subparser(subparsers)
        return subparsers

    def add_show_subparser(self, subparsers):
        cmd_show = subparsers.add_parser('show',
                                         help='show current statuses')
        cmd_show.set_defaults(func=self.show_running_jobs)
        show_subparsers = cmd_show.add_subparsers(title='show')
        show_running_jobs = show_subparsers.add_parser(
            'running-jobs',
            help='show the running jobs'
        )
        running_jobs_columns = list(self._show_running_jobs_columns().keys())
        show_running_jobs.add_argument(
            '--columns',
            help="comma separated list of columns to display (or 'ALL')",
            choices=running_jobs_columns.append('ALL'),
            default='name, worker.name, start_time, result'
        )
        # TODO: add filters such as queue, project, changeid etc
        show_running_jobs.set_defaults(func=self.show_running_jobs)

    def add_conf_check_subparser(self, subparsers):
        cmd_conf_check = subparsers.add_parser(
            'tenant-conf-check',
            help='validate the tenant configuration')
        cmd_conf_check.set_defaults(func=self.validate)

    def add_create_auth_token_subparser(self, subparsers):
        cmd_create_auth_token = subparsers.add_parser(
            'create-auth-token',
            help='create an Authentication Token for the web API',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
            Create an Authentication Token for the administration web API

            Create a bearer token that can be used to access Zuul's
            administration web API. This is typically used to delegate
            privileged actions such as enqueueing and autoholding to
            third parties, scoped to a single tenant.
            At least one authenticator must be configured with a secret
            that can be used to sign the token.'''))
        cmd_create_auth_token.add_argument(
            '--auth-config',
            help=('The authenticator to use. '
                  'Must match an authenticator defined in zuul\'s '
                  'configuration file.'),
            default='zuul_operator',
            required=True)
        cmd_create_auth_token.add_argument(
            '--tenant',
            help='tenant name',
            required=True)
        cmd_create_auth_token.add_argument(
            '--user',
            help=("The user's name. Used for traceability in logs."),
            default=None,
            required=True)
        cmd_create_auth_token.add_argument(
            '--expires-in',
            help=('Token validity duration in seconds '
                  '(default: %i)' % 600),
            type=int,
            default=600,
            required=False)
        cmd_create_auth_token.set_defaults(func=self.create_auth_token)

    def get_client(self):
        if self.args.zuul_url:
            self.log.debug('Zuul URL provided as argument, using REST client')
            self.log.warning('Using the REST client is deprecated, '
                             'use zuul-client instead')
            print('[DEPRECATED] The REST client is deprecated for this CLI. '
                  'Use `zuul-client` instead.')
            client = ZuulRESTClient(self.args.zuul_url,
                                    self.args.insecure_ssl,
                                    self.args.auth_token)
            return client
        conf_sections = self.config.sections()
        if 'gearman' in conf_sections:
            self.log.debug('gearman section found in config, using RPC client')
            server = self.config.get('gearman', 'server')
            port = get_default(self.config, 'gearman', 'port', 4730)
            ssl_key = get_default(self.config, 'gearman', 'ssl_key')
            ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
            ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')
            client = zuul.rpcclient.RPCClient(
                server, port, ssl_key,
                ssl_cert, ssl_ca,
                client_id=self.app_description)
        elif 'webclient' in conf_sections:
            self.log.debug('web section found in config, using REST client')
            self.log.warning('Using the REST client is deprecated, '
                             'use zuul-client instead')
            print('[DEPRECATED] The REST client is deprecated for this CLI. '
                  'Use `zuul-client` instead.')
            server = get_default(self.config, 'webclient', 'url', None)
            verify = get_default(self.config, 'webclient', 'verify_ssl',
                                 self.args.insecure_ssl)
            client = ZuulRESTClient(server, verify,
                                    self.args.auth_token)
        else:
            print('Unable to find a way to connect to Zuul, add a "gearman" '
                  'section to your configuration file')
            sys.exit(1)
        if server is None:
            print('Missing "server" configuration value')
            sys.exit(1)
        return client

    def create_auth_token(self):
        auth_section = ''
        for section_name in self.config.sections():
            if re.match(r'^auth ([\'\"]?)%s(\1)$' % self.args.auth_config,
                        section_name, re.I):
                auth_section = section_name
                break
        if auth_section == '':
            print('"%s" authenticator configuration not found.'
                  % self.args.auth_config)
            return False
        now = time.time()
        token = {'iat': now,
                 'exp': now + self.args.expires_in,
                 'iss': get_default(self.config, auth_section, 'issuer_id'),
                 'aud': get_default(self.config, auth_section, 'client_id'),
                 'sub': self.args.user,
                 'zuul': {'admin': [self.args.tenant, ]},
                }
        driver = get_default(
            self.config, auth_section, 'driver')
        if driver == 'HS256':
            key = get_default(self.config, auth_section, 'secret')
        elif driver == 'RS256':
            private_key = get_default(self.config, auth_section, 'private_key')
            try:
                with open(private_key, 'r') as pk:
                    key = pk.read()
            except Exception as e:
                print('Could not read private key at "%s": %s' % (private_key,
                                                                  e))
                return False
        else:
            print('Unknown or unsupported authenticator driver "%s"' % driver)
            return False
        try:
            auth_token = jwt.encode(token,
                                    key=key,
                                    algorithm=driver).decode('utf-8')
            print("Bearer %s" % auth_token)
            success = True
        except Exception as e:
            print("Error when generating Auth Token")
            print(e)
            success = False
        finally:
            return success

    def show_running_jobs(self):
        client = self.get_client()
        running_items = client.get_running_jobs()

        if len(running_items) == 0:
            print("No jobs currently running")
            return True

        all_fields = self._show_running_jobs_columns()
        fields = all_fields.keys()

        table = prettytable.PrettyTable(
            field_names=[all_fields[f]['title'] for f in fields])
        for item in running_items:
            for job in item['jobs']:
                values = []
                for f in fields:
                    v = job
                    for part in f.split('.'):
                        if hasattr(v, 'get'):
                            v = v.get(part, '')
                    if ('transform' in all_fields[f]
                        and callable(all_fields[f]['transform'])):
                        v = all_fields[f]['transform'](v)
                    if 'append' in all_fields[f]:
                        v += all_fields[f]['append']
                    values.append(v)
                table.add_row(values)
        print(table)
        return True

    def _epoch_to_relative_time(self, epoch):
        if epoch:
            delta = datetime.timedelta(seconds=(time.time() - int(epoch)))
            return babel.dates.format_timedelta(delta, locale='en_US')
        else:
            return "Unknown"

    def _boolean_to_yes_no(self, value):
        return 'Yes' if value else 'No'

    def _boolean_to_pass_fail(self, value):
        return 'Pass' if value else 'Fail'

    def _format_list(self, l):
        return ', '.join(l) if isinstance(l, list) else ''

    def _show_running_jobs_columns(self):
        """A helper function to get the list of available columns for
        `zuul show running-jobs`. Also describes how to convert particular
        values (for example epoch to time string)"""

        return {
            'name': {
                'title': 'Job Name',
            },
            'elapsed_time': {
                'title': 'Elapsed Time',
                'transform': self._epoch_to_relative_time
            },
            'remaining_time': {
                'title': 'Remaining Time',
                'transform': self._epoch_to_relative_time
            },
            'url': {
                'title': 'URL'
            },
            'result': {
                'title': 'Result'
            },
            'voting': {
                'title': 'Voting',
                'transform': self._boolean_to_yes_no
            },
            'uuid': {
                'title': 'UUID'
            },
            'execute_time': {
                'title': 'Execute Time',
                'transform': self._epoch_to_relative_time,
                'append': ' ago'
            },
            'start_time': {
                'title': 'Start Time',
                'transform': self._epoch_to_relative_time,
                'append': ' ago'
            },
            'end_time': {
                'title': 'End Time',
                'transform': self._epoch_to_relative_time,
                'append': ' ago'
            },
            'estimated_time': {
                'title': 'Estimated Time',
                'transform': self._epoch_to_relative_time,
                'append': ' to go'
            },
            'pipeline': {
                'title': 'Pipeline'
            },
            'canceled': {
                'title': 'Canceled',
                'transform': self._boolean_to_yes_no
            },
            'retry': {
                'title': 'Retry'
            },
            'number': {
                'title': 'Number'
            },
            'node_labels': {
                'title': 'Node Labels'
            },
            'node_name': {
                'title': 'Node Name'
            },
            'worker.name': {
                'title': 'Worker'
            },
            'worker.hostname': {
                'title': 'Worker Hostname'
            },
        }

    def validate(self):
        from zuul import scheduler
        from zuul import configloader
        sched = scheduler.Scheduler(self.config, testonly=True)
        self.configure_connections(source_only=True)
        sched.registerConnections(self.connections, load=False)
        loader = configloader.ConfigLoader(
            sched.connections, sched, None, None)
        tenant_config, script = sched._checkTenantSourceConf(self.config)
        unparsed_abide = loader.readConfig(tenant_config, from_script=script)
        try:
            for conf_tenant in unparsed_abide.tenants:
                loader.tenant_parser.getSchema()(conf_tenant)
            print("Tenants config validated with success")
            success = True
        except Exception as e:
            print("Error when validating tenants config")
            print(e)
            success = False
        finally:
            return success

    def configure_connections(self, source_only=False, include_drivers=None):
        self.connections = zuul.lib.connections.ConnectionRegistry()
        self.connections.configure(self.config, source_only, include_drivers)


def main():
    Client().main()
