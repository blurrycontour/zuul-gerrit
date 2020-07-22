# Copyright 2020 Red Hat Inc
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
import json
import sys
import datetime
import os
import requests


def usage(argv):
    two_weeks_ago = datetime.datetime.utcnow()- datetime.timedelta(days=14)
    parser = argparse.ArgumentParser(description="Look for unstrusted command in builds log")
    parser.add_argument("--since", default=two_weeks_ago, help="Date in YYYY-MM-DD format")
    parser.add_argument("zuul_url", help="The url of a zuul-web service")
    args = parser.parse_args(argv)

    args.zuul_url = args.zuul_url.rstrip("/")
    if not args.zuul_url.endswith("/api"):
        args.zuul_url += "/api"
    if not isinstance(args.since, datetime.datetime):
        args.since = datetime.datetime.strptime(args.since, "%Y-%m-%d")
    return args


def get_tenants(zuul_url):
    """ Fetch list of tenant names """
    is_witelabel = requests.get("%s/info" % zuul_url).json().get('tenant', None) is not None
    if is_witelabel:
        raise RuntimeError("Need multitenant api")
    return [tenant["name"] for tenant in requests.get("%s/tenants" % zuul_url).json()]


def is_build_in_range(build, since):
    """ Check if a build is in range """
    try:
        build_date = datetime.datetime.strptime(build["start_time"], "%Y-%m-%dT%H:%M:%S")
        return build_date > since
    except TypeError:
        return False


def get_builds(build_url, since):
    """ Fecth list of builds that are in range """
    builds = []
    pos = 0
    step = 50
    while not builds or is_build_in_range(builds[-1], since):
        url = "%s?skip=%d&limit=%d" % (build_url, pos, step)
        print("Querying %s" % url)
        builds += requests.get(url).json()
        pos += step
    return builds


def get_unique_builds(zuul_tenant_url, since):
    builds = dict()
    for build in get_builds("%s/builds" % zuul_tenant_url, since):
        if build["job_name"] not in builds:
              builds[build["job_name"]] = build
    return list(builds.values())


def download(source_url, local_filename):
    with requests.get(source_url, local_filename, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def download_build_job_output(zuul_build_url, local_path):
    build = requests.get(zuul_build_url).json()
    if not build.get("log_url"):
        return "No log url"
    try:
        download(build["log_url"] + "job-output.json", local_path)
    except Exception as e:
        return str(e)


def examine(path):
    data = json.load(open(path))
    to_fix = False
    for playbook in data:
        if playbook['trusted']:
            continue
        for play in playbook['plays']:
            for task in play['tasks']:
                for hostname, host in task['hosts'].items():
                    if hostname != 'localhost':
                        continue
                    if host['action'] in ['command', 'shell']:
                        print("Found disallowed task:")
                        print("  Playbook: %s" % playbook['playbook'])
                        print("  Role: %s" % task.get('role', {}).get('name'))
                        print("  Task: %s" % task.get('task', {}).get('name'))
                        to_fix = True
    return to_fix


def main(argv):
    args = usage(argv)
    tenants = get_tenants(args.zuul_url)
    to_fix = set()
    failed_to_examine = set()
    for tenant in tenants:
        if tenant != "zuul":
            continue
        zuul_tenant_url = args.zuul_url + "/tenant/" + tenant
        for build in get_unique_builds(zuul_tenant_url, args.since):
            local_path = build["uuid"] + ".json"
            build_url = zuul_tenant_url + "/build/" + build["uuid"]
            if not os.path.exists(local_path):
                err = download_build_job_output(build_url, local_path)
                if err:
                    failed_to_examine.add((build_url, err))
                    continue
            try:
                if not examine(local_path):
                    print("%s: ok" % build_url)
                else:
                    to_fix.add(build_url)
            except Exception as e:
                failed_to_examine.add((build_url, str(e)))

    if failed_to_examine:
        print("The following build couldn't be examined:")
        for build_url, err in failed_to_examine:
            print("%s: %s" % (build_url, err))
        if not to_fix:
            exit(1)

    if to_fix:
        print("The following build are using localhost command:")
        for build in to_fix:
            print(build.replace("/api/", "/t/"))
        exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
