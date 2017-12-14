# Copyright 2018 BMW Car IT GmbH
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

import logging.handlers

from zuul.ansible import paths
command = paths._import_ansible_action_plugin("command")


class ActionModule(command.ActionModule):

    def run(self, tmp=None, task_vars=None):
        if self._task.action in ('command', 'shell'):
            remote_port = logging.handlers.DEFAULT_TCP_LOGGING_PORT
            local_ports = self._task.args.pop('zuul_port_forwards', {})

            local_port = local_ports.get(
                self._connection._play_context.remote_addr)
            if local_port:
                if self._connection.transport == 'ssh':
                    ssh_extra_args = self._play_context.ssh_extra_args
                    if not self._play_context.ssh_extra_args:
                        ssh_extra_args = ''
                    ssh_extra_args += ' -R %s:localhost:%s' % (
                        remote_port,
                        local_port)
                    self._play_context.ssh_extra_args = ssh_extra_args
                    self._task.args['zuul_log_port'] = remote_port
                elif self._connection.transport == 'local':
                    self._task.args['zuul_log_port'] = local_port

        return super(ActionModule, self).run(tmp, task_vars)
