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

import imp
import os

import ansible.plugins.action


def _full_path(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _fail_dict(path, prefix='Accessing files from'):
    return dict(
        failed=True,
        path=path,
        msg="{prefix} outside the working dir {curdir} is prohibited".format(
            prefix=prefix,
            curdir=os.path.abspath(os.path.curdir)))


def _import_ansible_action_plugin(name):
    # Ansible forces the import of our action plugins
    # (zuul.ansible.action.foo) as ansible.plugins.action.foo, which
    # is the import path of the ansible implementation.  Our
    # implementations need to subclass that, but if we try to import
    # it with that name, we will get our own module.  This bypasses
    # Python's module namespace to load the actual ansible modules.
    # We need to give it a name, however.  If we load it with its
    # actual name, we will end up overwriting our module in Python's
    # namespace, causing infinite recursion.  So we supply an
    # otherwise unused name for the module:
    # zuul.ansible.protected.action.foo.

    return imp.load_module(
        'zuul.ansible.protected.action.' + name,
        *imp.find_module(name, ansible.plugins.action.__path__))


def _sanitize_filename(name):
    return ''.join(c for c in name if c.isalnum())
