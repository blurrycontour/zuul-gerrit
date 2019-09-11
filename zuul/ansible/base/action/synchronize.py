# Copyright 2016 Red Hat, Inc.
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

import os.path
from zuul.ansible import paths
synchronize = paths._import_ansible_action_plugin("synchronize")
from ansible.plugins.loader import connection_loader
from ansible import constants as C


class ActionModule(synchronize.ActionModule):

    def run(self, tmp=None, task_vars=None):
        if not paths._is_official_module(self):
            return paths._fail_module_dict(self._task.action)

        try:
            delegate_to = self._task.delegate_to
        except (AttributeError, KeyError):
            delegate_to = None

        if delegate_to and not paths._is_localhost_task(self):
            return super(ActionModule, self).run(tmp, task_vars)

        source = self._task.args.get('src', None)
        dest = self._task.args.get('dest', None)
        mode = self._task.args.get('mode', 'push')

        if 'rsync_opts' not in self._task.args:
            self._task.args['rsync_opts'] = []
        if '--safe-links' not in self._task.args['rsync_opts']:
            self._task.args['rsync_opts'].append('--safe-links')

        if mode == 'push' and not paths._is_safe_path(
                source, allow_trusted=True):
            return paths._fail_dict(source, prefix='Syncing files from')
        if mode == 'pull' and not paths._is_safe_path(dest):
            return paths._fail_dict(dest, prefix='Syncing files to')

        if self._connection.transport in ['kubectl']:
            # This is the minimal synchronize action for kubectl imported
            # from https://github.com/ansible/ansible/pull/62107
            # Remove this block once synchronize works with kubectl connection
            if source is None or dest is None:
                return dict(
                    failed=True,
                    msg="synchronize requires both src and dest parameters "
                    "are set")

            # Get the pod name
            inventory_hostname = task_vars.get('inventory_hostname')
            dest_host_inventory_vars = task_vars['hostvars'].get(
                inventory_hostname)
            try:
                dest_host = dest_host_inventory_vars['ansible_host']
            except KeyError:
                dest_host = dest_host_inventory_vars.get(
                    'ansible_ssh_host', inventory_hostname)

            if mode == 'push':
                dest = "%s:%s" % (dest_host, dest)
            else:
                source = "%s:%s" % (dest_host, source)
                # Remove non existing local basename from path
                if not os.path.exists(dest):
                    dest = os.path.dirname(dest)

            # We always want oc to be running from the executor
            self._play_context.shell = os.path.basename(C.DEFAULT_EXECUTABLE)
            self._play_context.executable = C.DEFAULT_EXECUTABLE
            self._connection = connection_loader.get(
                'local', self._play_context, self._connection._new_stdin)
            self._connection._remote_is_local = True
            self._override_module_replaced_vars(task_vars)

            # Execute the synchronize library module
            if task_vars is None:
                task_vars = dict()
            result = super(synchronize.ActionModule, self).run(tmp, task_vars)
            result.update(
                self._execute_module(
                    'synchronize',
                    module_args=dict(
                        _local_rsync_path='oc',
                        src=source,
                        dest=dest,
                        # Archive is set by default
                        archive=False,
                        delete=self._task.args.get('delete', False),
                        compress=self._task.args.get('compress', True)),
                    task_vars=task_vars))
            return result

        return super(ActionModule, self).run(tmp, task_vars)
