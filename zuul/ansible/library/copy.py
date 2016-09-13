#!/usr/bin/python

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

from ansible.module_utils.basic import _load_params


def main():
    params = _load_params()
    print '''
{{
  "msg": "Error: Use of the {module} module is forbidden",
  "failed": true
}}'''.format(module=params['_ansible_module_name'])


if __name__ == '__main__':
    main()
