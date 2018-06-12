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

import logging
import logging.config
import os
import traceback

from zuul.ansible import logconfig

from zuul.ansible import paths
command = paths._import_ansible_action_plugin("command")


class ActionModule(command.ActionModule):

    def run(self, tmp=None, task_vars=None):

        logging_config = logconfig.load_job_config(
            os.environ['ZUUL_JOB_LOG_CONFIG'])

        if self._display.verbosity > 2:
            logging_config.setDebug()

        logging_config.apply()

        logger = logging.getLogger('zuul.executor.ansible')

        logger.info("command: task.args = %s" % self._task.args)

        if 'zuul_log_id' not in self._task.args:
            trace = '\n'.join(traceback.format_stack())
            logger.info("missing zuul_log_id:\n%s" % trace)

        return super(ActionModule, self).run(tmp, task_vars)
