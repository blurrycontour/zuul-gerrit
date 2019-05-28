#!/usr/bin/env python3

import argparse
import os
import yaml
import sys

from Crypto.PublicKey import RSA
from Crypto.Hash import HMAC
from struct import pack
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor


class PRNG(object):

    def __init__(self, seed):
        self.index = 0
        self.seed = seed
        self.buffer = b''

    def __call__(self, n):
        while len(self.buffer) < n:
            self.buffer += HMAC.new(self.seed +
                                    pack('<I', self.index)).digest()
            self.index += 1
        result, self.buffer = self.buffer[:n], self.buffer[n:]
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
    seed = HMAC.new(master_key + project.encode('utf-8')).digest()
    repokey = RSA.generate(4096, randfunc=PRNG(seed))

    targetdir = os.path.join(destroot, 'secrets', 'project', project)
    os.makedirs(targetdir, mode=0o700, exist_ok=True)

    keyfile = '%s/0.pem' % targetdir
    print('  %s' % keyfile)

    with open(keyfile, 'w') as f:
        f.write(repokey.exportKey().decode())


def main():
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

    print('Write version identifier')
    versionfile = os.path.join(destroot, '.version')
    with open(versionfile, 'w') as f:
        f.write('1')

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
