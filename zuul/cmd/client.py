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

import argparse
import babel.dates
import datetime
import json
import logging
import prettytable
import sys
import urllib.parse
import urllib.request
import time


import zuul.rpcclient
import zuul.cmd
import zuul.web
from zuul.lib.config import get_default


class Client(zuul.cmd.ZuulApp):
    log = logging.getLogger("zuul.Client")

    def parse_arguments(self):
        parser = argparse.ArgumentParser(
            description='Zuul Project Gating System Client.')
        parser.add_argument('-c', dest='config',
                            help='specify the config file')
        parser.add_argument('--web-url', help='the zuul-web host url'),
        parser.add_argument('-v', dest='verbose', action='store_true',
                            help='verbose output')
        parser.add_argument('--version', dest='version', action='version',
                            version=self._get_version(),
                            help='show zuul version')

        subparsers = parser.add_subparsers(title='commands',
                                           description='valid commands',
                                           help='additional help')

        cmd_autohold = subparsers.add_parser(
            'autohold', help='hold nodes for failed job')
        cmd_autohold.add_argument('--tenant', help='tenant name',
                                  required=True)
        cmd_autohold.add_argument('--project', help='project name',
                                  required=True)
        cmd_autohold.add_argument('--job', help='job name',
                                  required=True)
        cmd_autohold.add_argument('--reason', help='reason for the hold',
                                  required=True)
        cmd_autohold.add_argument('--count',
                                  help='number of job runs (default: 1)',
                                  required=False, type=int, default=1)
        cmd_autohold.set_defaults(func=self.autohold)

        cmd_autohold_list = subparsers.add_parser(
            'autohold-list', help='list autohold requests')
        cmd_autohold_list.set_defaults(func=self.autohold_list)

        cmd_enqueue = subparsers.add_parser('enqueue', help='enqueue a change')
        cmd_enqueue.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_enqueue.add_argument('--trigger', help='trigger name',
                                 required=True)
        cmd_enqueue.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_enqueue.add_argument('--project', help='project name',
                                 required=True)
        cmd_enqueue.add_argument('--change', help='change id',
                                 required=True)
        cmd_enqueue.set_defaults(func=self.enqueue)

        cmd_enqueue = subparsers.add_parser('enqueue-ref',
                                            help='enqueue a ref')
        cmd_enqueue.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_enqueue.add_argument('--trigger', help='trigger name',
                                 required=True)
        cmd_enqueue.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_enqueue.add_argument('--project', help='project name',
                                 required=True)
        cmd_enqueue.add_argument('--ref', help='ref name',
                                 required=True)
        cmd_enqueue.add_argument(
            '--oldrev', help='old revision',
            default='0000000000000000000000000000000000000000')
        cmd_enqueue.add_argument(
            '--newrev', help='new revision',
            default='0000000000000000000000000000000000000000')
        cmd_enqueue.set_defaults(func=self.enqueue_ref)

        cmd_promote = subparsers.add_parser('promote',
                                            help='promote one or more changes')
        cmd_promote.add_argument('--tenant', help='tenant name',
                                 required=True)
        cmd_promote.add_argument('--pipeline', help='pipeline name',
                                 required=True)
        cmd_promote.add_argument('--changes', help='change ids',
                                 required=True, nargs='+')
        cmd_promote.set_defaults(func=self.promote)

        cmd_show = subparsers.add_parser('show',
                                         help='valid show subcommands')
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

        show_builds = show_subparsers.add_parser('builds',
                                                 help='show the builds')
        show_builds.add_argument("tenant", nargs=1,
                                 help='tenant\'s name build')
        for filter_name in zuul.web.SqlHandler.filters:
            if filter_name == "tenant":
                continue
            show_builds.add_argument('--%s' % filter_name, action='append',
                                     help="filter by %s" % filter_name)
        show_builds.add_argument('--limit', type=int, help="Limit the query")
        show_builds.add_argument('--skip', type=int, help="Skip rows")
        show_builds.set_defaults(func=self.show_builds)

        show_jobs = show_subparsers.add_parser('jobs',
                                               help='show the jobs defined')
        show_jobs.add_argument("tenant", nargs=1,
                               help='tenant\'s name build')
        show_jobs.set_defaults(func=self.show_jobs)

        self.args = parser.parse_args()
        if not getattr(self.args, 'func', None):
            parser.print_help()
            sys.exit(1)
        if self.args.func == self.enqueue_ref:
            if self.args.oldrev == self.args.newrev:
                parser.error("The old and new revisions must not be the same.")

    def setup_logging(self):
        """Client logging does not rely on conf file"""
        if self.args.verbose:
            logging.basicConfig(level=logging.DEBUG)

    def main(self):
        self.parse_arguments()
        self.read_config()
        self.setup_logging()

        self.server = self.config.get('gearman', 'server')
        self.port = get_default(self.config, 'gearman', 'port', 4730)
        self.ssl_key = get_default(self.config, 'gearman', 'ssl_key')
        self.ssl_cert = get_default(self.config, 'gearman', 'ssl_cert')
        self.ssl_ca = get_default(self.config, 'gearman', 'ssl_ca')

        if self.args.func():
            sys.exit(0)
        else:
            sys.exit(1)

    def autohold(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        r = client.autohold(tenant=self.args.tenant,
                            project=self.args.project,
                            job=self.args.job,
                            reason=self.args.reason,
                            count=self.args.count)
        return r

    def autohold_list(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        autohold_requests = client.autohold_list()

        if len(autohold_requests.keys()) == 0:
            print("No autohold requests found")
            return True

        table = prettytable.PrettyTable(
            field_names=['Tenant', 'Project', 'Job', 'Count', 'Reason'])

        for key, value in autohold_requests.items():
            # The key comes to us as a CSV string because json doesn't like
            # non-str keys.
            tenant_name, project_name, job_name = key.split(',')
            count, reason = value
            table.add_row([tenant_name, project_name, job_name, count, reason])
        print(table)
        return True

    def enqueue(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        r = client.enqueue(tenant=self.args.tenant,
                           pipeline=self.args.pipeline,
                           project=self.args.project,
                           trigger=self.args.trigger,
                           change=self.args.change)
        return r

    def enqueue_ref(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        r = client.enqueue_ref(tenant=self.args.tenant,
                               pipeline=self.args.pipeline,
                               project=self.args.project,
                               trigger=self.args.trigger,
                               ref=self.args.ref,
                               oldrev=self.args.oldrev,
                               newrev=self.args.newrev)
        return r

    def promote(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        r = client.promote(tenant=self.args.tenant,
                           pipeline=self.args.pipeline,
                           change_ids=self.args.changes)
        return r

    def show_running_jobs(self):
        client = zuul.rpcclient.RPCClient(
            self.server, self.port, self.ssl_key, self.ssl_cert, self.ssl_ca)
        running_items = client.get_running_jobs()

        if len(running_items) == 0:
            print("No jobs currently running")
            return True

        all_fields = self._show_running_jobs_columns()
        if self.args.columns.upper() == 'ALL':
            fields = all_fields.keys()
        else:
            fields = [f.strip().lower() for f in self.args.columns.split(',')
                      if f.strip().lower() in all_fields.keys()]

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

    def print_web_query(self, path, fields, params={}, limit=None, skip=None):
        if limit is not None:
            params.append(('limit', limit))
        if skip is not None:
            params.append(('skip', skip))
        if not self.args.web_url:
            self.args.web_url = "http://localhost:%s" % (
                get_default(self.config, 'web', 'port', 9000))
        url = "%s%s%s" % (self.args.web_url, path,
                          urllib.parse.urlencode(params))
        self.log.info("Fetching %s" % url)
        try:
            with urllib.request.urlopen(url) as f:
                jobs = json.loads(f.read().decode('utf-8'))
        except Exception:
            self.log.exception("Couldn't fetch %s" % url)
            sys.exit(1)
        table = prettytable.PrettyTable(field_names=fields)
        for job in jobs:
            values = []
            for field in fields:
                values.append(job[field])
            table.add_row(values)
        print(table)
        return True

    def show_builds(self):
        params = {}
        for filter_name in zuul.web.SqlHandler.filters:
            if hasattr(self.args, filter_name) and \
               getattr(self.args, filter_name):
                for param in getattr(self.args, filter_name):
                    params[filter_name] = param
        return self.print_web_query(
            "/%s/builds.json?" % self.args.tenant[0], [
                "job_name", "project", "pipeline",
                "change", "patchset", "ref",
                "duration", "result", "log_url", "end_time"],
            params=params, limit=self.args.limit, skip=self.args.skip)

    def show_jobs(self):
        return self.print_web_query(
            "/%s/jobs.json?" % self.args.tenant[0], ["name", "description"])

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


def main():
    client = Client()
    client.main()


if __name__ == "__main__":
    sys.path.insert(0, '.')
    main()
