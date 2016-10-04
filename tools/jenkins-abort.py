#!/usr/bin/env python
# Copyright (c) 2016 Hewlett-Packard Enterprise Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import logging
import re
import time

import requests


parser = argparse.ArgumentParser()
parser.add_argument('--jenkins-user', dest='user',
                    help='Jenkins user')
parser.add_argument('--jenkins-password', dest='password',
                    help='Jenkins password')
parser.add_argument('--zuul-host', dest='host',
                    default='localhost',
                    help='Host running zuul server')
parser.add_argument('--poll-wait', dest='wait',
                    default=30, type=int,
                    help='Seconds to wait between polling zuul')
parser.add_argument('--log-file', dest='logfile',
                    help='Path for the logfile. If unset, output will be '
                         'logged to stdout.')
parser.add_argument('--log-level', dest='loglevel',
                    default='info',
                    help='Level to log at.')
parser.add_argument('--dry-run', '--noop', dest='noop',
                    action='store_true',
                    help='Do not send abort POST request to jenkins master.')
parser.add_argument('--abort-all', '--all', dest='all',
                    action='store_true',
                    help='Abort all jobs, regardless of failure detection, '
                         'project whitelist, or pipeline whitelist.')
parser.add_argument('--project-regex', dest='projects',
                    default=[], nargs='*', metavar='REGEX',
                    help='Whitelist projects based on given regex. '
                         'If multiple expressions are given, any match will '
                         'result in whitelisting.')
parser.add_argument('--pipeline-regex', dest='pipelines',
                    default=['^check', '^gate'], nargs='*', metavar='REGEX',
                    help='Whitelist pipelines based on given regex. '
                         'If multiple expressions are given, any match will '
                         'result in whitelisting.')
args = parser.parse_args()

status_url = 'http://%s/status.json' % args.host

loglevel = getattr(logging, args.loglevel.upper())
if args.logfile:
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=loglevel,
                        filename=args.logfile)
else:
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=loglevel)
logging.getLogger("requests").setLevel(logging.WARNING)


def match_project_whitelist(project):
    if args.all or not args.projects:
        return True

    for regex in args.projects:
        if re.search(regex, project):
            return True

    return False


def match_pipeline_whitelist(pipeline):
    if args.all or not args.pipelines:
        return True

    for regex in args.pipelines:
        if re.search(regex, pipeline):
            return True

    return False


def abort_job(job):
    if job['result'] is None:
        url = job['url']
        if url is None:
            logging.error("job %s has no url" % job['name'])
        elif url.startswith('https://'):
            auth = ''
            if args.user and args.password:
                auth = '%s:%s@' % (args.user, args.password)

            abort_url = 'https://%s%sstop' % (auth, url[8:])
            logging.info("ABORT: %s" % abort_url)

            if not args.noop:
                ubuntu_certs = '/etc/ssl/certs'
                response = requests.post(abort_url, verify=ubuntu_certs)
                if response and response.status_code != 200:
                    logging.error("HTTP %s: %s" %
                                  (response.status_code, response.text))


def process_pipeline(pipeline):
    logging.debug("Entering pipeline %s" % pipeline['name'])
    for cq in pipeline['change_queues']:
        for h in cq['heads']:
            for head in h:
                if not head['active']:
                    logging.debug("Skipping inactive %s (active=%s)" %
                                  (head['id'], head['active']))
                    continue

                if not match_project_whitelist(head['project']):
                    logging.debug("Skipping project %s" % head['project'])
                    continue

                failed = False
                for job in head['jobs']:
                    if args.all:
                        abort_job(job)
                        continue

                    elif job['result'] == 'FAILURE' and job['voting']:
                        failed = True
                        logging.info("%s has failed for %s" %
                                     (job['name'], head['url']))
                        break

                if failed:
                    logging.info("At least one job has failed for %s" %
                                 head['url'])
                    for job in head['jobs']:
                        abort_job(job)


while True:
    try:
        logging.debug("Polling zuul status")
        json_data = requests.get(status_url)
        status = json.loads(json_data.text)
    except (ValueError, requests.exceptions.ConnectionError):
        logging.exception("Failed to load zuul status")
        time.sleep(args.wait)
        continue

    for pipeline in status['pipelines']:
        if not match_pipeline_whitelist(pipeline['name']):
            logging.debug("Skipping pipeline %s" % pipeline['name'])
            continue

        process_pipeline(pipeline)

    time.sleep(args.wait)
