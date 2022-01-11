# Copyright 2022 Acme Gating, LLC
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

# Inspect ZK contents like zk-shell; handles compressed and sharded
# data.

import argparse
import pathlib
import cmd
import sys
import textwrap
import zlib

import kazoo.client


def resolve_path(path, rest):
    newpath = path / rest
    newparts = []
    for part in newpath.parts:
        if part == '.':
            continue
        elif part == '..':
            newparts.pop()
        else:
            newparts.append(part)
    return pathlib.PurePosixPath(*newparts)


class REPL(cmd.Cmd):
    def __init__(self, args):
        self.path = pathlib.PurePosixPath('/')
        super().__init__()
        kwargs = {}
        if args.cert:
            kwargs['use_ssl'] = True
            kwargs['keyfile'] = args.key
            kwargs['certfile'] = args.cert
            kwargs['ca'] = args.ca
        self.client = kazoo.client.KazooClient(args.host, **kwargs)
        self.client.start()

    @property
    def prompt(self):
        return f'{self.path}> '

    def do_EOF(self, path):
        sys.exit(0)

    def do_ls(self, path):
        'List znodes: ls [PATH]'
        if path:
            mypath = self.path / path
        else:
            mypath = self.path
        for child in self.client.get_children(str(mypath)):
            print(child)

    def do_cd(self, path):
        'Change the working path: cd PATH'
        if path:
            self.path = resolve_path(self.path, path)

    def do_pwd(self):
        'Print the working path'
        print(self.path)

    def help_get(self):
        print(textwrap.dedent(self.do_get.__doc__))

    def do_get(self, args):
        """\
        Get znode value: get PATH [-v]

        -v: output metadata about the path
        """
        args = args.split(' ')
        path = args[0]
        args = args[1:]
        path = resolve_path(self.path, path)
        compressed_data, zstat = self.client.get(str(path))
        was_compressed = False
        try:
            data = zlib.decompress(compressed_data)
            was_compressed = True
        except zlib.error:
            data = compressed_data
        if '-v' in args:
            print(f'Compressed: {was_compressed}')
            print(f'Size: {len(data)}')
            print(f'Compressed size: {len(compressed_data)}')
            print(f'Zstat: {zstat}')
        print(data)

    def help_unshard(self):
        print(textwrap.dedent(self.do_unshard.__doc__))

    def do_unshard(self, args):
        """\
        Get the unsharded value: get PATH [-v]

        -v: output metadata about the path
        """
        args = args.split(' ')
        path = args[0]
        args = args[1:]
        path = resolve_path(self.path, path)

        shards = sorted(self.client.get_children(str(path)))
        compressed_data = b''
        data = b''
        for shard in shards:
            d, _ = self.client.get(str(path / shard))
            compressed_data += d
        if data:
            data = zlib.decompress(compressed_data)

        if '-v' in args:
            print(f'Size: {len(data)}')
            print(f'Compressed size: {len(compressed_data)}')
        print(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='ZK host string')
    parser.add_argument('--cert', help='Path to TLS certificate')
    parser.add_argument('--key', help='Path to TLS key')
    parser.add_argument('--ca', help='Path to TLS CA cert')
    args = parser.parse_args()

    repl = REPL(args)
    repl.cmdloop()


if __name__ == '__main__':
    main()
