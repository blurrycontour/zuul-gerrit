#!/usr/bin/python

# Copyright (c) 2016 IBM Corp.
# Copyright (c) 2016 Red Hat
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

import datetime


class Console(object):
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.logfile = open(self.path, 'a', 0)
        return self

    def __exit__(self, etype, value, tb):
        self.logfile.close()

    def addLine(self, ln):
        ts = datetime.datetime.now()
        outln = '%s | %s' % (str(ts), ln)
        self.logfile.write(outln)


def log(msg, path):
    if not isinstance(msg, list):
        msg = [msg]
    with Console(path) as console:
        for line in msg:
            console.addLine("[Zuul] %s\n" % line)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            msg=dict(required=True, type='raw'),
            path=dict(default='/tmp/console.html'),
        )
    )

    p = module.params
    log(p['msg'], p['path'])
    module.exit_json(changed=True)

from ansible.module_utils.basic import *  # noqa

if __name__ == '__main__':
    main()
