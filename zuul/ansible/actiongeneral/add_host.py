# Copyright 2016 Red Hat, Inc.
# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
# Copyright 2012, Seth Vidal <skvidal@fedoraproject.org>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Zuul modification: persist host accross run phases

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import yaml
from zuul.ansible import paths

from ansible.errors import AnsibleError
from ansible.module_utils.six import string_types
from ansible.plugins.action import ActionBase
from ansible.parsing.utils.addresses import parse_address

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class ActionModule(ActionBase):
    ''' Create inventory hosts and groups in the memory inventory'''

    # We need to be able to modify the inventory
    BYPASS_HOST_LOOP = True
    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        # Begin zuul changes
        if not paths._is_official_module(self):
            return paths._fail_module_dict(self._task.action)

        play_vars = self._task._variable_manager.get_vars()
        inventory_path = play_vars["ansible_inventory_sources"][0]
        trusted = play_vars.get('zuul_execution_trusted')
        if trusted != "True":
            return dict(
                failed=True,
                msg="Adding hosts to the inventory is prohibited")
        # End zuul changes

        self._supports_check_mode = True

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        # Parse out any hostname:port patterns
        new_name = self._task.args.get('name', self._task.args.get(
            'hostname', self._task.args.get('host', None)))

        if new_name is None:
            result['failed'] = True
            result['msg'] = 'name or hostname arg needs to be provided'
            return result

        display.vv("creating host via 'add_host': hostname=%s" % new_name)

        try:
            name, port = parse_address(new_name, allow_ranges=False)
        except Exception:
            # not a parsable hostname, but might still be usable
            name = new_name
            port = None

        if port:
            self._task.args['ansible_ssh_port'] = port

        groups = self._task.args.get('groupname', self._task.args.get(
            'groups', self._task.args.get('group', '')))
        # add it to the group if that was specified
        new_groups = []
        if groups:
            if isinstance(groups, list):
                group_list = groups
            elif isinstance(groups, string_types):
                group_list = groups.split(",")
            else:
                raise AnsibleError(
                    "Groups must be specified as a list.", obj=self._task)

            for group_name in group_list:
                if group_name not in new_groups:
                    new_groups.append(group_name.strip())

        # Add any variables to the new_host
        host_vars = dict()
        special_args = frozenset(('name', 'hostname', 'groupname', 'groups'))
        for k in self._task.args.keys():
            if k not in special_args:
                host_vars[k] = self._task.args[k]

        result['changed'] = True
        result['add_host'] = dict(
            host_name=name, groups=new_groups, host_vars=host_vars)

        # Begin zuul changes
        inventory = yaml.safe_load(open(inventory_path))
        # Convert values to string
        inventory['all']['hosts'][str(new_name)] = dict(map(
            lambda x: (str(x[0]), str(x[1])), host_vars.items()))
        with open(inventory_path, 'w') as inventory_yaml:
            inventory_yaml.write(yaml.safe_dump(
                inventory, default_flow_style=False))
        # End zuul changes
        return result
