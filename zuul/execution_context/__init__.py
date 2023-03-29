# Copyright 2016 Red Hat, Inc.
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

import abc
import os
import os.path
import re


class BaseExecutionContext(object, metaclass=abc.ABCMeta):
    """The execution interface returned by a wrapper.

    Wrapper drivers return instances which implement this interface.

    It is used to hold information and aid in the execution of a
    single command.

    """
    release_file_re = re.compile(r'^\W+-release$')

    def __init__(self):
        self.mounts_map = {
            'ro': [
                '/usr',
                '/lib',
                '/bin',
                '/sbin',
                '/etc/ld.so.cache',
                '/etc/resolv.conf',
                '/etc/hosts',
                '/etc/localtime',
                '{ssh_auth_sock}',
            ],
            'rw': [
                '{work_dir}',
            ],
        }
        for path in ['/lib64',
                     '/etc/nsswitch.conf',
                     '/etc/lsb-release.d',
                     '/etc/alternatives',
                     '/etc/ssl/certs',
                     '/etc/subuid',
                     ]:
            if os.path.exists(path):
                self.mounts_map['ro'].append(path)
        for fn in os.listdir('/etc'):
            if self.release_file_re.match(fn):
                path = os.path.join('/etc', fn)
                self.mounts_map['ro'].append(path)

    @abc.abstractmethod
    def getPopen(self, **kwargs):
        """Create and return a subprocess.Popen factory wrapped however the
        driver sees fit.

        This method is required by the interface

        :arg dict kwargs: key/values for use by driver as needed

        :returns: a callable that takes the same args as subprocess.Popen
        :rtype: Callable
        """
        pass

    def getMountPaths(self, **kwargs):
        paths = [x.format(**kwargs)
                 for x in self.mounts_map['ro'] + self.mounts_map['rw']]
        return paths
