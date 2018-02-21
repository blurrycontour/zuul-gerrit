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


import tempfile
from ansible import constants as C
from zuul.ansible import paths
template = paths._import_ansible_action_plugin("template")


class ActionModule(template.ActionModule):

    def _find_needle(self, dirname, needle):
        return paths._safe_find_needle(
            super(ActionModule, self), dirname, needle)

    def run(self, tmp=None, task_vars=None):
        if not paths._is_official_module(self):
            return paths._fail_module_dict(self._task.action)

        # HACK(tobiash): Set the default dir to the local_tmp. This is a
        # workaround for making template action respect local_tmp in
        # ansible 2.4. Otherwise the template module is broken as starting with
        # ansible 2.4 it defers the copying to the copy module which itself
        # does the safe path check again with a temp file not residing in the
        # work dir.
        #
        # For 2.5 this is fixed in
        # https://github.com/ansible/ansible/pull/35005
        tempfile.tempdir = C.DEFAULT_LOCAL_TMP

        return super(ActionModule, self).run(tmp, task_vars)
