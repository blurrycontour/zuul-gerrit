# Copyright 2024 Acme Gating, LLC
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
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()
        results = super(ActionModule, self).run(tmp, task_vars)

        args = self._task.args
        path = args.get('path')
        if not path:
            path = os.path.join(os.environ['ZUUL_JOBDIR'], 'work',
                                'inventory.json')

        if os.path.exists(path):
            os.unlink(path)

        results['changed'] = True
        return results
