#!/usr/bin/env python3

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
import os
import yaml

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac
from Crypto.PublicKey import RSA
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor


class RandomNumberGenerator(object):

    def __init__(self, seed):
        self.buffer = b''
        self.hmac = hmac.HMAC(seed, hashes.SHA512(), backend=default_backend())

    def __call__(self, n):
        while len(self.buffer) < n:
            self.hmac.update(b'something')
            self.buffer += self.hmac.copy().finalize()
        result = self.buffer[:n]
        self.buffer = self.buffer[n:]
        return result


def get_projects(tenant_config):
    result = []

    for element in tenant_config:
        tenant = element.get('tenant', None)
        if not tenant:
            continue

        sources = tenant.get('source')
        if not sources:
            continue

        for source, source_elements in sources.items():
            for trusted, repos in source_elements.items():
                for repo in repos:
                    if isinstance(repo, str):
                        reponame = repo
                    else:
                        reponame = list(repo.keys())[0]
                    result.append('{}/{}'.format(source, reponame))

    return result


def load_master_key(master_key_file):
    with open(master_key_file, 'r') as f:
        lines = []
        for line in f.readlines():
            if line.startswith('-----'):
                continue
            lines.append(line)

        return b64decode('\n'.join(lines))


def write_key(project, destroot, master_key):
    mac = hmac.HMAC(master_key, hashes.SHA512(), backend=default_backend())
    mac.update(project.encode('utf-8'))
    seed = mac.finalize()

    repokey = RSA.generate(4096, randfunc=RandomNumberGenerator(seed))

    projectdir = os.path.split(project)[0]

    os.makedirs(os.path.join(destroot, projectdir), mode=0o700, exist_ok=True)

    keyfile = '%s.pem' % os.path.join(destroot, project)
    print('  %s' % keyfile)

    with open(keyfile, 'w') as f:
        f.write(repokey.exportKey().decode())


if __name__ == '__main__':

    description = 'Derive reproducible private keys from a master key and a ' \
                  'zuul tenant config.'

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('tenant_config', type=str,
                        help='zuul tenant configuration')
    parser.add_argument('master_key', type=str,
                        help='master encryption key')
    parser.add_argument('-d', type=str, default='/var/lib/zuul/keys',
                        help='target root dir')

    args = parser.parse_args()

    tenant_config_file = args.tenant_config
    master_key_file = args.master_key
    destroot = args.d

    with open(tenant_config_file, 'r') as f:
        tenant_config = yaml.safe_load(f)

    projects = get_projects(tenant_config)

    master_key = load_master_key(master_key_file)

    executor = ThreadPoolExecutor()

    print('Generating keys')
    futures = []
    for project in projects:
        futures.append(
            executor.submit(write_key, project, destroot, master_key))

    for future in futures:
        future.result()

