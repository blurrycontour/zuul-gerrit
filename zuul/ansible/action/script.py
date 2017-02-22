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


from zuul.ansible import paths
copy = paths._import_ansible_action_plugin("copy")


class ActionModule(copy.ActionModule):

    def run(self, tmp=None, task_vars=None):

        # the script name is the first item in the raw params, so we split it
        # out now so we know the file name we need to transfer to the remote,
        # and everything else is an argument to the script which we need later
        # to append to the remote command
        parts = self._task.args.get('_raw_params', '').strip().split()
        source = parts[0]

        if not paths._is_safe_path(source):
            return paths._fail_dict(source)
        return super(ActionModule, self).run(tmp, task_vars)
