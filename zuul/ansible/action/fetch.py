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


from . import paths
fetch = paths._import_ansible_action_plugin("fetch")


class ActionModule(fetch.ActionModule):

    def run(self, tmp=None, task_vars=None):

        dest = self._task.args.get('dest', None)

        if dest and not paths._is_safe_path(dest):
            return paths._fail_dict(dest)
        return super(ActionModule, self).run(tmp, task_vars)
