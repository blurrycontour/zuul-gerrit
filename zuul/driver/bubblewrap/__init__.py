# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
# Copyright 2016 Red Hat, Inc.
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
import grp
import logging
import os
import pwd
import subprocess

from zuul.driver import (Driver, WrapperInterface)


class BubblewrapDriver(Driver, WrapperInterface):
    name = 'bubblewrap'
    log = logging.getLogger("zuul.BubblewrapDriver")

    bwrap_command = [
        'bwrap',
        '--dir', '/tmp',
        '--tmpfs', '/tmp',
        '--dir', '/var',
        '--dir', '/var/tmp',
        '--dir', '/run/user/{uid}',
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/lib', '/lib',
        '--ro-bind', '/lib64', '/lib64',
        '--ro-bind', '/bin', '/bin',
        '--ro-bind', '/sbin', '/sbin',
        '--ro-bind', '/etc/resolv.conf', '/etc/resolv.conf',
        '--ro-bind', '{ansible_dir}', '{ansible_dir}',
        '--dir', '{work_dir}',
        '--bind', '{work_dir}', '{work_dir}',
        '--dev', '/dev',
        '--dir', '{user_home}',
        '--chdir', '/',
        '--unshare-all',
        '--share-net',
        '--uid', '{uid}',
        '--gid', '{gid}',
        '--file', '{uid_fd}', '/etc/passwd',
        '--file', '{gid_fd}', '/etc/group',
    ]

    def reconfigure(self, tenant):
        pass

    def stop(self):
        pass

    def getPopen(self, **kwargs):
        # Need users and groups
        uid = os.getuid()
        passwd = pwd.getpwuid(uid)
        passwd_bytes = b':'.join(
            ['{}'.format(x).encode('utf8') for x in passwd])
        (passwd_r, passwd_w) = os.pipe()
        os.write(passwd_w, passwd_bytes)
        os.close(passwd_w)

        gid = os.getgid()
        group = grp.getgrgid(gid)
        group_bytes = b':'.join(
            ['{}'.format(x).encode('utf8') for x in group])
        group_r, group_w = os.pipe()
        os.write(group_w, group_bytes)
        os.close(group_w)

        kwargs = dict(kwargs)  # Don't update passed in dict
        kwargs['uid'] = uid
        kwargs['gid'] = gid
        kwargs['uid_fd'] = passwd_r
        kwargs['gid_fd'] = group_r
        kwargs['user_home'] = passwd.pw_dir
        command = [x.format(**kwargs) for x in self.bwrap_command]

        def wrapped_popen(args, *sub_args, **kwargs):
            args = command + args
            return subprocess.Popen(args, *sub_args, **kwargs)

        return wrapped_popen


def main(args=None):
    driver = BubblewrapDriver()

    parser = argparse.ArgumentParser()
    parser.add_argument('work_dir')
    parser.add_argument('ansible_dir')
    parser.add_argument('run_args', nargs='+')
    cli_args = parser.parse_args()

    popen = driver.getPopen(work_dir=cli_args.work_dir,
                            ansible_dir=cli_args.ansible_dir)
    x = popen(cli_args.run_args)
    x.wait()


if __name__ == '__main__':
    main()
