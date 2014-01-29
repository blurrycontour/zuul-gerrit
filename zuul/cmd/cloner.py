#!/usr/bin/env python
#
# Copyright 2014 Antoine "hashar" Musso
# Copyright 2014 Wikimedia Foundation Inc.
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

import argparse
import os
import sys

from zuul.lib.cloner import Cloner

ZUUL_ENV_SUFFIXES = (
    'branch',
    'change',
    'patchset',
    'pipeline',
    'project',
    'ref',
    'url',
)


def get_version():
    """Zuul version suitable for display to user"""
    from zuul.version import version_info as zuul_version_info
    return "Zuul version: %s" % zuul_version_info.version_string()


def parse_args():
    """Parse command line arguments and returns argparse structure"""
    parser = argparse.ArgumentParser(
        description='Zuul Project Gating System Cloner.')
    parser.add_argument('-m', '--map', dest='clone_map_file',
                        help='specifiy clone map file')
    parser.add_argument('--workspace', dest='workspace',
                        default=os.getcwd(),
                        help='Where to clone repositories too')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='verbose output')
    parser.add_argument('--version', dest='version', action='version',
                        version=get_version(),
                        help='show zuul version')
    parser.add_argument('projects', nargs='+',
                        help='Gerrit projects to clone')

    project_env = parser.add_argument_group(
        'project tuning'
    )
    project_env.add_argument(
        '--branch',
        help=('Branch to checkout instead of Zuul selected branch, '
              'for example to specify an alternate branch to test '
              'client library compatibility.')
    )

    zuul_env = parser.add_argument_group(
        'zuul environnement',
        'Let you override $ZUUL_* environnement variables.'
    )
    for zuul_suffix in ZUUL_ENV_SUFFIXES:
        env_name = 'ZUUL_%s' % zuul_suffix.upper()
        zuul_env.add_argument(
            '--zuul-%s' % zuul_suffix, metavar='$' + env_name,
            default=os.environ.get(env_name)
        )

    args = parser.parse_args()
    zuul_missing = [zuul_opt for zuul_opt, val in vars(args).items()
                    if zuul_opt.startswith('zuul') and val is None]
    if zuul_missing:
        parser.error(("Some Zuul parameters are not properly set:\n\t%s\n"
                      "Define them either via environment variables or using "
                      "options above." %
                      "\n\t".join(sorted(zuul_missing))))
    return args


def main():
    args = parse_args()
    cloner = Cloner(args)
    cloner.execute()


if __name__ == "__main__":
    sys.path.insert(0, '.')
    main()
