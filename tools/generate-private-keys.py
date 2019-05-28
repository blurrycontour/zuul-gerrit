#!/usr/bin/env python3

import argparse
import configparser
import os
import yaml
import sys
import logging
import time
import io

from Crypto.PublicKey import RSA
from Crypto.Hash import HMAC
from struct import pack
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
import paramiko

from zuul.lib.keystorage import KeyStorage
from zuul.zk import ZooKeeperClient
from zuul.lib import encryption


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
                    result.append((source, reponame))

    return result


def load_master_key(master_key_file):
    with open(master_key_file, 'r') as f:
        lines = []
        for line in f.readlines():
            if line.startswith('-----'):
                continue
            lines.append(line)

        return b64decode('\n'.join(lines))


def write_key(keystore, connection_name, project_name, master_key):

    existing = keystore.loadProjectsSecretsKeys(
        connection_name, project_name)
    if existing is None:
        print("Generating secrets key for %s %s" % (
            connection_name, project_name))
        seed = HMAC.new(master_key + project_name.encode('utf-8')).digest()
        repokey = RSA.generate(4096, randfunc=PRNG(seed))
        pem_private_key = repokey.exportKey().decode().encode('utf-8')
        private_key, public_key = encryption.deserialize_rsa_keypair(
            pem_private_key)
        pem_private_key = encryption.serialize_rsa_private_key(
            private_key, keystore.password_bytes)

        key_version = 0
        key_created = int(time.time())
        keystore._storeSecretsKey(connection_name, project_name,
                                  pem_private_key, key_version,
                                  key_created)

    existing = keystore.loadProjectSSHKeys(
        connection_name, project_name)
    if existing is None:
        print("Generating SSH key for %s %s" % (
            connection_name, project_name))
        seed = HMAC.new(master_key + project_name.encode('utf-8')).digest()
        repokey = RSA.generate(2048, randfunc=PRNG(seed))
        pem_private_key = repokey.exportKey().decode()
        with io.StringIO(pem_private_key) as o:
            rsakey = paramiko.RSAKey.from_private_key(o)

        key_version = 0
        key_created = int(time.time())
        keystore._storeSSHKey(connection_name, project_name,
                              rsakey, key_version,
                              key_created)


def read_config(args):
    safe_env = {
        k: v for k, v in os.environ.items()
        if k.startswith('ZUUL_')
    }
    config = configparser.ConfigParser(safe_env)
    if args.config:
        locations = [args.config]
    else:
        locations = ['/etc/zuul/zuul.conf',
                     '~/zuul.conf']
    for fp in locations:
        if os.path.exists(os.path.expanduser(fp)):
            config.read(os.path.expanduser(fp))
            return config
    raise Exception("Unable to locate config file in %s" % locations)


def main():
    logging.basicConfig(level=logging.INFO)

    description = 'Derive reproducible private keys from a master key and a ' \
                  'zuul tenant config.'

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('tenant_config', type=str,
                        help='zuul tenant configuration')
    parser.add_argument('master_key', type=str,
                        help='master encryption key')
    parser.add_argument('-c', dest='config', type=str,
                        help='zuul.conf location')

    args = parser.parse_args()

    tenant_config_file = args.tenant_config
    master_key_file = args.master_key
    config = read_config(args)

    zk_client = ZooKeeperClient.fromConfig(config)
    zk_client.connect()
    try:
        password = config["keystore"]["password"]
    except KeyError:
        raise RuntimeError("No key store password configured!")
    keystore = KeyStorage(zk_client, password=password)

    with open(tenant_config_file, 'r') as f:
        tenant_config = yaml.safe_load(f)

    projects = get_projects(tenant_config)

    master_key = load_master_key(master_key_file)

    executor = ThreadPoolExecutor()

    print('Generating keys')
    futures = []
    for (connection, project) in projects:
        futures.append(
            executor.submit(
                write_key, keystore, connection, project, master_key))

    for future in futures:
        future.result()

    return 0


if __name__ == '__main__':
    sys.exit(main())
