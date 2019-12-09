#!/usr/bin/env python3
# Copyright 2019 BMW Group
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

from concurrent.futures.thread import ThreadPoolExecutor
from urllib.parse import urljoin

import requests

# TODO: make base url configurable
baseurl = 'https://example.org/api/'


def ansible_version(tenant, job, session):
    url = urljoin(baseurl, f'tenant/{tenant}/job/{job}')
    try:
        r = session.get(url)
    except requests.exceptions.ConnectionError as e:
        ansible_version(tenant, job, session)
        return
    r.raise_for_status()
    versions = [v['ansible_version'] for v in r.json()
                if v['ansible_version']]
    if not versions:
        return
    print(f'  {job}: {versions}')


def main():
    session = requests.session()

    url = urljoin(baseurl, 'tenants')
    r = session.get(url)
    r.raise_for_status()

    with ThreadPoolExecutor(max_workers=8) as tp:
        tenants = (t['name'] for t in r.json())
        for tenant in tenants:
            tasks = []
            print(tenant)
            url = urljoin(baseurl, 'tenant/%s/jobs' % tenant)
            r = session.get(url)
            r.raise_for_status()
            jobs = (j['name'] for j in r.json())
            for job in jobs:
                tasks.append(tp.submit(ansible_version, tenant, job, session))

            for task in tasks:
                task.result()


if __name__ == "__main__":
    main()
