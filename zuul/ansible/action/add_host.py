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
add_host = paths._import_ansible_action_plugin("add_host")


class ActionModule(add_host.ActionModule):

    def run(self, tmp=None, task_vars=None):
        if self._task.args.get('ansible_connection') == 'kubectl':
            # Allow kubectl connection to be added from untrusted-project
            # This could be removed when a trusted phase is allowed to inject
            # dynamic host in the inventory (for container-native where the
            # pod is created by the job)
            return super(ActionModule, self).run(tmp, task_vars)

        return dict(
            failed=True,
            msg="Adding hosts to the inventory is prohibited")
