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

import multiprocessing
import time

from ansible.plugins import action
from ansible.utils.vars import merge_hash



def run_module(func, send_pipe, tmp, task_vars):
    try:
        results = func(tmp=tmp, task_vars=task_vars)
    except Exception as e:
        results = {
            'msg': str(e),
            'failed': True
        }
    send_pipe.send(results)


class ActionModule(action.ActionBase):

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        if self._task.async and not self._task.poll:
            # TODO(mordred) If async is given and no poll, that means someone
            # intends to do an async_status later. In that case, our fancy
            # here is going to go boom, and we need to defer to the actual
            # async module. Both don't know how to do that currently, nor do
            # I care, so we'll just bail
            return {
                'msg': 'async tasks in fire and forget mode are not supported',
                'failed': True
            }
        # Accessing private members is eversomuchfun
        fact_cache = self._task._variable_manager._nonpersistent_fact_cache
        hostname = task_vars['vars']['inventory_hostname']
        # TODO(mordred) There is a possibility of this failing open, which is
        # not the desire. That is, we have a get because we don't have an
        # elapsed time set on the first task in a playbook, since we set it
        # at the end of the previous task. If a bug arises in the callback
        # plugin, this will happily report 0. Obviously we can just avoid
        # bugs in the callback plugin, but maybe let's not do it.
        elapsed = fact_cache[hostname].get('elapsed_time', 0)
        play_timeout = task_vars['zuul']['timeout']
        if play_timeout is None:
            return {
                'msg': 'zuul requires a global timeout to be set',
                'failed': True
            }
        task_timeout = self._task.async or play_timeout
        self._display.vvvv(
            "play: {play_timeout} task: {task_timeout}"
            " elapsed {elapsed}".format(
                play_timeout=play_timeout,
                elapsed=elapsed,
                task_timeout=task_timeout))
        # The timeout for this task should be the lesser of the remaining
        # time on the play_timeout or an explicit timeout requested in an
        # async call if it's lower than the remainder
        timeout = play_timeout - elapsed
        timeout = task_timeout if task_timeout < timeout else timeout

        # Set this, because we're not actually doing the ansible async dance.
        self._task.async = False

        results = super(ActionModule, self).run(tmp, task_vars)
        # Strip these so that we don't leak hidden things
        if 'invocation' in results:
            results['invocation'].pop('module_args', None)

        (recv_pipe, send_pipe) = multiprocessing.Pipe(duplex=False)
        proc = multiprocessing.Process(
            target=run_module,
            args=(self._execute_module, send_pipe, tmp, task_vars))
        start_time = time.time()
        proc.start()
        interval = self._task.poll or 1

        while True:
            time.sleep(interval)
            if not proc.is_alive():
                break
            if (time.time() - start_time) >= timeout:
                # Note: this will orphan child processes - so the ssh command
                # the task is running won't get hard stopped. This needs to
                # be solved for long-lived slaves people are managing.
                proc.terminate()
                return {
                    'msg': 'Task timeed out',
                    'failed': True
                }
        proc.join()
        results = merge_hash(results, recv_pipe.recv())
        for field in ('_ansible_notify',):
            results.pop(field, None)

        return results
