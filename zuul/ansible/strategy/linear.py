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

from ansible.errors import AnsibleError, AnsibleAssertionError
from ansible.executor.play_iterator import PlayIterator
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_text
from ansible.playbook.block import Block
from ansible.playbook.included_file import IncludedFile
from ansible.playbook.task import Task
from ansible.plugins.loader import action_loader
from ansible.plugins.strategy import StrategyBase
from ansible.template import Templar

from zuul.ansible import logconfig

from zuul.ansible import paths
linear = paths._import_ansible_strategy_plugin("linear")

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class StrategyModule(linear.StrategyModule):

    def _queue_task(self, host, task, task_vars, play_context):
        logging_config = logconfig.load_job_config(
            os.environ['ZUUL_JOB_LOG_CONFIG'])

        if self._display.verbosity > 2:
            logging_config.setDebug()

        logging_config.apply()

        logger = logging.getLogger('zuul.executor.ansible')

        logger.info("_queue_task: run %s" % task.args)

        super(StrategyModule, self)._queue_task(
            host, task, task_vars, play_context)
