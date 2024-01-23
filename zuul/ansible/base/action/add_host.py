# Copyright (c) 2017 Red Hat
# Copyright 2023-2024 Acme Gating, LLC
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
import json
import tempfile

from ansible.template import recursive_check_defined

from zuul.ansible import paths

add_host = paths._import_ansible_action_plugin("add_host")


class ActionModule(add_host.ActionModule):

    def run(self, tmp=None, task_vars=None):
        args = self._task.args
        # If there are any "zuul" variables, pop them.  Varibles named
        # "zuul" are reserved in zuul, so they are useless as
        # hostvars anyway.
        zuul = args.pop('zuul', {})

        temp_hostvars = {}
        special_args = frozenset(('name', 'hostname', 'groupname', 'groups'))
        for k in args.keys():
            if k not in special_args:
                temp_hostvars[k] = args[k]

        # Freeze the hostvars to approximates what happens in
        # zuul_freeze.  This is mostly for consistency between
        # playbook runs.  Since it could be subverted by a "manual"
        # edit of the inventory result file, it's not necessary for
        # security; for that we rely on secrets being marked !unsafe.
        with self._templar.set_temporary_context(
                available_variables=temp_hostvars):
            for var in temp_hostvars.keys():
                try:
                    # Template the variable (convert_bare means treat a
                    # bare variable name as {{ var }}.
                    value = self._templar.template(var, convert_bare=True)
                    recursive_check_defined(value)
                    args[var] = value
                except Exception:
                    del args[var]

        # Let the superclass do its thing.
        ret = super(ActionModule, self).run(tmp, task_vars)

        # If the user didn't ask us to save the host, do nothing.
        if not zuul.get('persist_host'):
            return ret

        # Verify that the superclass decided we should actually add a
        # host.
        add_host_data = ret.get('add_host')
        if not add_host_data:
            return ret
        host_name = add_host_data.get('host_name')
        if not host_name:
            return ret

        # If the host already exists, do nothing.
        existing_hosts = self._templar.template("{{ hostvars }}",
                                                convert_bare=True)
        if host_name in existing_hosts:
            return ret

        path = zuul.get('path')
        if not path:
            path = os.path.join(os.environ['ZUUL_JOBDIR'], 'work',
                                'inventory.json')

        # Read existing data.
        file_data = {'hosts': []}
        if os.path.exists(path):
            with open(path, 'r') as f:
                file_data = json.load(f)

        # Append our new host.
        file_data['hosts'].append(add_host_data)

        # Write a new copy of the file.
        workdir = os.path.dirname(path)
        (f, tmp_path) = tempfile.mkstemp(dir=workdir)
        try:
            f = os.fdopen(f, 'w')
            json.dump(file_data, f)
            f.close()
            os.rename(tmp_path, path)
        except Exception:
            os.unlink(tmp_path)
            raise

        return ret
