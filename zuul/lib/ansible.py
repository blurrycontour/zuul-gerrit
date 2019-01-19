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
import abc
import concurrent.futures
import logging
import os
import subprocess
import sys


class ManagedAnsibleBase(metaclass=abc.ABCMeta):
    log = logging.getLogger('zuul.manage_ansible')

    def __init__(self, ansible_root):
        self.version = None
        self._requirements = None
        self._ansible_root = ansible_root

    def ensure_ansible(self, upgrade=False):
        self._ensure_venv()

        self.log.info('Installing ansible %s, extra packages: %s',
                      self.version, self.extra_packages)
        self._run_pip(self._requirements + self.extra_packages,
                      upgrade=upgrade)

    def _run_pip(self, requirements, upgrade=False):
        cmd = [self.python_path, '-m', 'pip', 'install']
        if upgrade:
            cmd.append('-U')
        cmd.extend(requirements)
        self.log.debug('Running pip: %s', ' '.join(cmd))

        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.returncode != 0:
            raise Exception('Package installation failed with exit code %s:\n'
                            'stdout:\n%s\n'
                            'stderr:\n%s' % (p.returncode, p.stdout.decode(),
                                             p.stderr.decode()))
        self.log.debug('Successfully installed packages %s', requirements)

    def _ensure_venv(self):
        if os.path.exists(self.python_path):
            self.log.debug(
                'Virtual environment %s already existing', self.venv_path)
            return

        self.log.info('Creating venv %s', self.venv_path)

        python_executable = sys.executable
        if hasattr(sys, 'real_prefix'):
            # We're inside a virtual env and the venv module behaves strange
            # if we're calling it from there so default to
            # <real_prefix>/bin/python3
            python_executable = os.path.join(sys.real_prefix, 'bin', 'python3')

        # We don't use directly the venv module here because its behavior is
        # broken if we're already in a virtual environment.
        cmd = [python_executable, '-mvenv', self.venv_path]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if p.returncode != 0:
            raise Exception('venv creation failed with exit code %s:\n'
                            'stdout:\n%s\n'
                            'stderr:\n%s' % (p.returncode, p.stdout.decode(),
                                             p.stderr.decode()))

        self.log.debug('Updating pip')
        self._run_pip(['pip'], upgrade=True)

    @property
    def venv_path(self):
        return os.path.join(self._ansible_root, self.version)

    @property
    def python_path(self):
        return os.path.join(self.venv_path, 'bin', 'python')

    @property
    def extra_packages(self):
        mapping = str.maketrans({
            '.': None,
            '-': '_',
        })
        env_var = 'ANSIBLE_%s_EXTRA_PACKAGES' % self.version.upper().translate(
            mapping)

        packages = os.environ.get(env_var)
        if packages:
            return packages.strip().split(' ')

        return []


class ManagedAnsibleBase25(ManagedAnsibleBase):
    log = logging.getLogger('zuul.manage_ansible.25')

    def __init__(self, ansible_root):
        super().__init__(ansible_root)
        self.version = '2.5'
        self._requirements = ['ansible>=2.5.1<2.6']


class ManagedAnsibleBase26(ManagedAnsibleBase):
    log = logging.getLogger('zuul.manage_ansible.26')

    def __init__(self, ansible_root):
        super().__init__(ansible_root)
        self.version = '2.6'
        self._requirements = ['ansible>=2.6<2.7']


class ManagedAnsibleBase27(ManagedAnsibleBase):
    log = logging.getLogger('zuul.manage_ansible.27')

    def __init__(self, ansible_root):
        super().__init__(ansible_root)
        self.version = '2.7'
        self._requirements = ['ansible>=2.7<2.8']


class ManagedAnsibleBaseDevel(ManagedAnsibleBase):
    log = logging.getLogger('zuul.manage_ansible.devel')

    def __init__(self, ansible_root):
        super().__init__(ansible_root)
        self.version = 'devel'
        self._requirements = [
            'git+https://github.com/ansible/ansible@devel#egg=ansible'
        ]


class AnsibleManager:

    def __init__(self, ansible_root):
        self.ansible_root = ansible_root
        self.supported_versions = {
            '2.5': ManagedAnsibleBase25(ansible_root),
            '2.6': ManagedAnsibleBase26(ansible_root),
            '2.7': ManagedAnsibleBase27(ansible_root),

            # Enable devel only for testing
            # 'devel': ManagedAnsibleBaseDevel(ansible_root),
        }
        self.default_version = '2.5'
        self.deprecated_versions = []

    def install(self, upgrade=False):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(a.ensure_ansible, upgrade): a
                       for a in self.supported_versions.values()}
            for future in concurrent.futures.as_completed(futures):
                version = futures[future]
                try:
                    future.result()
                except Exception:
                    logging.getLogger('main').exception(
                        'Got exception while processing ansible %s',
                        version.version)

    def getAnsibleCommand(self, version=None, command='ansible-playbook'):
        version = version or self.default_version

        ansible = self.supported_versions.get(version)
        if not ansible:
            raise Exception('Requested ansible version %s not found' % version)

        return os.path.join(ansible.venv_path, 'bin', command)
