# Copyright 2019 BMW Group
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

import tempfile

import ansible_mitogen.plugins.strategy.mitogen_linear
import mitogen.unix
import logging

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class StrategyModule(
    ansible_mitogen.plugins.strategy.mitogen_linear.StrategyModule):
    pass


# patch mitogen logging
old_setup = ansible_mitogen.logging.setup


def logging_setup():
    old_setup()

    l_mitogen = logging.getLogger('mitogen')
    # If we run ansible in verbose mode mitogen sets the mitogen backend
    # logging to debug which is way to excessive and causes problems. Reset
    # that to info in this case.
    if display.verbosity > 2:
        l_mitogen.setLevel(logging.INFO)


def make_safe_socket_path():
    return tempfile.mktemp(
        prefix='mitogen_unix_',
        suffix='.sock',
        dir='/tmp')


ansible_mitogen.logging.setup = logging_setup

# patch mitogen.unix.make_socket_path as it relies on the $TMP env var which
# might be rather lenghty, and the AF_UNIX path is limited to 107 chars on
# linux (even less on other *nix'es). So we put the sockets under '/tmp'.
mitogen.unix.make_socket_path = make_safe_socket_path
