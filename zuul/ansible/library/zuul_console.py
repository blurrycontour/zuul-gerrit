#!/usr/bin/python

# Copyright (c) 2016 IBM Corp.
#
# This module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys


def daemonize():
    # A really basic daemonize method that should work well enough for
    # now in this circumstance. Based on the public domain code at:
    # http://web.archive.org/web/20131017130434/http://www.jejik.com/articles/2007/02/a_simple_unix_linux_daemon_in_python/

    pid = os.fork()
    if pid > 0:
        return True

    os.chdir('/')
    os.setsid()
    os.umask(0)

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    sys.stdout.flush()
    sys.stderr.flush()
    i = open('/dev/null', 'r')
    o = open('/dev/null', 'a+')
    e = open('/dev/null', 'a+', 0)
    os.dup2(i.fileno(), sys.stdin.fileno())
    os.dup2(o.fileno(), sys.stdout.fileno())
    os.dup2(e.fileno(), sys.stderr.fileno())
    return False


def test():
    s = log_streamer.get_node_log_streamer()
    s.serve_forever()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            path=dict(default=None, type='str'),
            port=dict(default=None, type='int'),
        )
    )

    p = module.params
    kwargs = {}
    for key in ('path', 'port'):
        if key in p:
            kwargs[key] = p[key]

    if daemonize():
        module.exit_json()

    s = log_streamer.get_node_log_streamer()
    s.serve_forever()

from ansible.module_utils.basic import *  # noqa
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import log_streamer

if __name__ == '__main__':
    main()
