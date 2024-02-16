# Copyright 2018 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import io
import json
import logging
import os
import re
import textwrap
from datetime import datetime, timedelta

from tests.base import AnsibleZuulTestCase


class FunctionalZuulStreamMixIn:
    tenant_config_file = 'config/remote-zuul-stream/main.yaml'
    # This should be overriden in child classes.
    ansible_version = 'X'
    ansible_core_version = 'X.Y'

    def _setUp(self):
        self.log_console_port = 19000 + int(
            self.ansible_core_version.split('.')[1])
        self.executor_server.log_console_port = self.log_console_port
        self.wait_timeout = 180
        self.fake_nodepool.remote_ansible = True
        # This catches the Ansible output; rather than the callback
        # output captured in the job log.  For example if the callback
        # fails, there will be an error output in this stream.
        self.logger = logging.getLogger('zuul.AnsibleJob')
        self.console_output = io.StringIO()
        self.logger.addHandler(logging.StreamHandler(self.console_output))

        ansible_remote = os.environ.get('ZUUL_REMOTE_IPV4')
        self.assertIsNotNone(ansible_remote)

    def _run_job(self, job_name, create=True, split='false'):
        # Keep the jobdir around so we can inspect contents if an
        # assert fails. It will be cleaned up anyway as it is contained
        # in a tmp dir which gets cleaned up after the test.
        self.executor_server.keep_jobdir = True

        # Output extra ansible info so we might see errors.
        self.executor_server.verbose = True
        if create:
            conf = textwrap.dedent(
                """
                - job:
                    name: {job_name}
                    run: playbooks/{job_name}.yaml
                    ansible-version: {version}
                    ansible-split-streams: {split}
                    vars:
                      test_console_port: {console_port}
                    roles:
                      - zuul: org/common-config
                    nodeset:
                      nodes:
                        - name: compute1
                          label: whatever
                        - name: controller
                          label: whatever

                - project:
                    check:
                      jobs:
                        - {job_name}
                """.format(
                    job_name=job_name,
                    version=self.ansible_version,
                    split=split,
                    console_port=self.log_console_port))
        else:
            conf = textwrap.dedent(
                """
                - project:
                    check:
                      jobs:
                        - {job_name}
                """.format(job_name=job_name))
        file_dict = {'zuul.yaml': conf}
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A',
                                           files=file_dict)
        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        job = self.getJobFromHistory(job_name)
        return job

    def _get_job_output(self, build):
        path = os.path.join(self.jobdir_root, build.uuid,
                            'work', 'logs', 'job-output.txt')
        with open(path) as f:
            return f.read()

    def _get_job_json(self, build):
        path = os.path.join(self.jobdir_root, build.uuid,
                            'work', 'logs', 'job-output.json')
        with open(path) as f:
            return json.loads(f.read())

    def _assertLogLine(self, line, log, full_match=True):
        pattern = (r'^\d\d\d\d-\d\d-\d\d \d\d:\d\d\:\d\d\.\d\d\d\d\d\d \| %s%s'
                   % (line, '$' if full_match else ''))
        log_re = re.compile(pattern, re.MULTILINE)
        m = log_re.search(log)
        if m is None:
            raise Exception("'%s' not found in log" % (line,))

    def assertLogLineStartsWith(self, line, log):
        self._assertLogLine(line, log, full_match=False)

    def assertLogLine(self, line, log):
        self._assertLogLine(line, log, full_match=True)

    def _getLogTime(self, line, log):
        pattern = (r'^(\d\d\d\d-\d\d-\d\d \d\d:\d\d\:\d\d\.\d\d\d\d\d\d)'
                   r' \| %s\n'
                   r'(\d\d\d\d-\d\d-\d\d \d\d:\d\d\:\d\d\.\d\d\d\d\d\d)'
                   % line)
        log_re = re.compile(pattern, re.MULTILINE)
        m = log_re.search(log)
        if m is None:
            raise Exception("'%s' not found in log" % (line,))
        else:
            date1 = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
            date2 = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S.%f")
            return (date1, date2)

    def test_command(self):
        job = self._run_job('command')
        with self.jobLog(job):
            build = self.history[-1]
            self.assertEqual(build.result, 'SUCCESS')

            console_output = self.console_output.getvalue()
            # This should be generic enough to match any callback
            # plugin failures, which look something like
            #
            #  [WARNING]: Failure using method (v2_runner_on_ok) in \
            #                                                  callback plugin
            #  (<ansible.plugins.callback.zuul_stream.CallbackModule object at'
            #  0x7f89f72a20b0>): 'dict' object has no attribute 'startswith'"
            #  Callback Exception:
            #  ...
            #
            self.assertNotIn('[WARNING]: Failure using method', console_output)

            text = self._get_job_output(build)
            data = self._get_job_json(build)

            token_stdout = "Standard output test {}".format(
                self.history[0].jobdir.src_root)
            token_stderr = "Standard error test {}".format(
                self.history[0].jobdir.src_root)
            result = data[0]['plays'][1]['tasks'][2]['hosts']['compute1']
            self.assertEqual("\n".join((token_stdout, token_stderr)),
                             result['stdout'])
            self.assertEqual("", result['stderr'])

            self.assertLogLine(
                r'RUN START: \[untrusted : review.example.com/org/project/'
                r'playbooks/command.yaml@master\]', text)
            self.assertLogLine(r'PLAY \[all\]', text)
            self.assertLogLine(
                r'Ansible version={}'.format(self.ansible_core_version), text)
            self.assertLogLine(r'TASK \[Show contents of first file\]', text)
            self.assertLogLine(r'controller \| command test one', text)
            self.assertLogLine(
                r'controller \| ok: Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'TASK \[Show contents of second file\]', text)
            self.assertLogLine(r'compute1 \| command test two', text)
            self.assertLogLine(r'controller \| command test two', text)
            self.assertLogLine(r'compute1 \| This is a rescue task', text)
            self.assertLogLine(r'controller \| This is a rescue task', text)
            self.assertLogLine(r'compute1 \| This is an always task', text)
            self.assertLogLine(r'controller \| This is an always task', text)
            self.assertLogLine(r'compute1 \| This is a handler', text)
            self.assertLogLine(r'controller \| This is a handler', text)
            self.assertLogLine(r'controller \| First free task', text)
            self.assertLogLine(r'controller \| Second free task', text)
            self.assertLogLine(r'controller \| This is a shell task after an '
                               'included role', text)
            self.assertLogLine(r'compute1 \| This is a shell task after an '
                               'included role', text)
            self.assertLogLine(r'controller \| This is a command task after '
                               'an included role', text)
            self.assertLogLine(r'compute1 \| This is a command task after an '
                               'included role', text)
            self.assertLogLine(r'controller \| This is a shell task with '
                               'delegate compute1', text)
            self.assertLogLine(r'controller \| This is a shell task with '
                               'delegate controller', text)
            self.assertLogLine(r'compute1 \| item_in_loop1', text)
            self.assertLogLine(r'compute1 \| ok: Item: item_in_loop1 '
                               r'Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'compute1 \| item_in_loop2', text)
            self.assertLogLine(r'compute1 \| ok: Item: item_in_loop2 '
                               r'Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'compute1 \| failed_in_loop1', text)
            self.assertLogLine(r'compute1 \| ok: Item: failed_in_loop1 '
                               r'Result: 1', text)
            self.assertLogLine(r'compute1 \| failed_in_loop2', text)
            self.assertLogLine(r'compute1 \| ok: Item: failed_in_loop2 '
                               r'Result: 1', text)
            self.assertLogLine(r'compute1 \| transitive-one', text)
            self.assertLogLine(r'compute1 \| transitive-two', text)
            self.assertLogLine(r'compute1 \| transitive-three', text)
            self.assertLogLine(r'compute1 \| transitive-four', text)
            self.assertLogLine(
                r'controller \| ok: Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine('PLAY RECAP', text)
            self.assertLogLine(
                r'controller \| ok: \d+ changed: \d+ unreachable: 0 failed: 0 '
                'skipped: 2 rescued: 1 ignored: 0', text)
            self.assertLogLine(
                r'RUN END RESULT_NORMAL: \[untrusted : review.example.com/'
                r'org/project/playbooks/command.yaml@master]', text)
            time1, time2 = self._getLogTime(r'TASK \[Command Not Found\]',
                                            text)
            self.assertLess((time2 - time1) / timedelta(milliseconds=1),
                            9000)

            # This is from the debug: msg='{{ ansible_version }}'
            # testing raw variable output.  To make it version
            # agnostic, match just the start of
            #  compute1 | ok: {'string': '2.9.27'...

            # NOTE(ianw) 2022-08-24 : I don't know why the callback
            # for debug: msg= doesn't put the hostname first like
            # other output. Undetermined if bug or feature.
            self.assertLogLineStartsWith(
                r"""\{'string': '\d.""", text)
            # ... handling loops is a different path, and that does
            self.assertLogLineStartsWith(
                r"""compute1 \| ok: \{'string': '\d.""", text)

    def test_command_split_streams(self):
        job = self._run_job('command', split='true')
        with self.jobLog(job):
            build = self.history[-1]
            self.assertEqual(build.result, 'SUCCESS')

            console_output = self.console_output.getvalue()
            # This should be generic enough to match any callback
            # plugin failures, which look something like
            #
            #  [WARNING]: Failure using method (v2_runner_on_ok) in \
            #                                                  callback plugin
            #  (<ansible.plugins.callback.zuul_stream.CallbackModule object at'
            #  0x7f89f72a20b0>): 'dict' object has no attribute 'startswith'"
            #  Callback Exception:
            #  ...
            #
            self.assertNotIn('[WARNING]: Failure using method', console_output)

            text = self._get_job_output(build)
            data = self._get_job_json(build)

            token_stdout = "Standard output test {}".format(
                self.history[0].jobdir.src_root)
            token_stderr = "Standard error test {}".format(
                self.history[0].jobdir.src_root)
            result = data[0]['plays'][1]['tasks'][2]['hosts']['compute1']
            self.assertEqual(token_stdout, result['stdout'])
            self.assertEqual(token_stderr, result['stderr'])

            self.assertLogLine(
                r'RUN START: \[untrusted : review.example.com/org/project/'
                r'playbooks/command.yaml@master\]', text)
            self.assertLogLine(r'PLAY \[all\]', text)
            self.assertLogLine(
                r'Ansible version={}'.format(self.ansible_core_version), text)
            self.assertLogLine(r'TASK \[Show contents of first file\]', text)
            self.assertLogLine(r'controller \| command test one', text)
            self.assertLogLine(
                r'controller \| ok: Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'TASK \[Show contents of second file\]', text)
            self.assertLogLine(r'compute1 \| command test two', text)
            self.assertLogLine(r'controller \| command test two', text)
            self.assertLogLine(r'compute1 \| This is a rescue task', text)
            self.assertLogLine(r'controller \| This is a rescue task', text)
            self.assertLogLine(r'compute1 \| This is an always task', text)
            self.assertLogLine(r'controller \| This is an always task', text)
            self.assertLogLine(r'compute1 \| This is a handler', text)
            self.assertLogLine(r'controller \| This is a handler', text)
            self.assertLogLine(r'controller \| First free task', text)
            self.assertLogLine(r'controller \| Second free task', text)
            self.assertLogLine(r'controller \| This is a shell task after an '
                               'included role', text)
            self.assertLogLine(r'compute1 \| This is a shell task after an '
                               'included role', text)
            self.assertLogLine(r'controller \| This is a command task after '
                               'an included role', text)
            self.assertLogLine(r'compute1 \| This is a command task after an '
                               'included role', text)
            self.assertLogLine(r'controller \| This is a shell task with '
                               'delegate compute1', text)
            self.assertLogLine(r'controller \| This is a shell task with '
                               'delegate controller', text)
            self.assertLogLine(r'compute1 \| item_in_loop1', text)
            self.assertLogLine(r'compute1 \| ok: Item: item_in_loop1 '
                               r'Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'compute1 \| item_in_loop2', text)
            self.assertLogLine(r'compute1 \| ok: Item: item_in_loop2 '
                               r'Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine(r'compute1 \| failed_in_loop1', text)
            self.assertLogLine(r'compute1 \| ok: Item: failed_in_loop1 '
                               r'Result: 1', text)
            self.assertLogLine(r'compute1 \| failed_in_loop2', text)
            self.assertLogLine(r'compute1 \| ok: Item: failed_in_loop2 '
                               r'Result: 1', text)
            self.assertLogLine(r'compute1 \| transitive-one', text)
            self.assertLogLine(r'compute1 \| transitive-two', text)
            self.assertLogLine(r'compute1 \| transitive-three', text)
            self.assertLogLine(r'compute1 \| transitive-four', text)
            self.assertLogLine(
                r'controller \| ok: Runtime: \d:\d\d:\d\d\.\d\d\d\d\d\d', text)
            self.assertLogLine('PLAY RECAP', text)
            self.assertLogLine(
                r'controller \| ok: \d+ changed: \d+ unreachable: 0 failed: 0 '
                'skipped: 2 rescued: 1 ignored: 0', text)
            self.assertLogLine(
                r'RUN END RESULT_NORMAL: \[untrusted : review.example.com/'
                r'org/project/playbooks/command.yaml@master]', text)
            time1, time2 = self._getLogTime(r'TASK \[Command Not Found\]',
                                            text)
            self.assertLess((time2 - time1) / timedelta(milliseconds=1),
                            9000)

            # This is from the debug: msg='{{ ansible_version }}'
            # testing raw variable output.  To make it version
            # agnostic, match just the start of
            #  compute1 | ok: {'string': '2.9.27'...

            # NOTE(ianw) 2022-08-24 : I don't know why the callback
            # for debug: msg= doesn't put the hostname first like
            # other output. Undetermined if bug or feature.
            self.assertLogLineStartsWith(
                r"""\{'string': '\d.""", text)
            # ... handling loops is a different path, and that does
            self.assertLogLineStartsWith(
                r"""compute1 \| ok: \{'string': '\d.""", text)

    def test_module_exception(self):
        job = self._run_job('module_failure_exception')
        with self.jobLog(job):
            build = self.history[-1]
            self.assertEqual(build.result, 'FAILURE')

            text = self._get_job_output(build)
            self.assertLogLine(r'TASK \[Module failure\]', text)
            self.assertLogLine(
                r'controller \| MODULE FAILURE:', text)
            self.assertLogLine(
                r'controller \| Exception: This module is broken', text)

    def test_module_no_result(self):
        job = self._run_job('module_failure_no_result')
        with self.jobLog(job):
            build = self.history[-1]
            self.assertEqual(build.result, 'FAILURE')

            text = self._get_job_output(build)
            self.assertLogLine(r'TASK \[Module failure\]', text)

            regex = r'controller \|   "msg": "New-style module did not ' \
                r'handle its own exit"'
            self.assertLogLine(regex, text)


class TestZuulStream8(AnsibleZuulTestCase, FunctionalZuulStreamMixIn):
    ansible_version = '8'
    ansible_core_version = '2.15'

    def setUp(self):
        super().setUp()
        self._setUp()


class TestZuulStream9(AnsibleZuulTestCase, FunctionalZuulStreamMixIn):
    ansible_version = '9'
    ansible_core_version = '2.16'

    def setUp(self):
        super().setUp()
        self._setUp()
