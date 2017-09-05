#!/usr/bin/env python
# Copyright 2017 Red Hat
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
import shutil

REPO_SRC_DIR = "~zuul/src/git.openstack.org/"


def parse_args():
    ZUUL_ENV_SUFFIXES = ('branch', 'ref', 'url', 'project', 'newrev')

    parser = argparse.ArgumentParser()

    # Ignored arguments
    parser.add_argument('--color', dest='color', action='store_true',
                        help='IGNORED')
    parser.add_argument('--cache-dir', dest='cache_dir', help='IGNORED')
    parser.add_argument('git_base_url', help='IGNORED')
    parser.add_argument('--branch', help='IGNORED')
    parser.add_argument('--project-branch', nargs=1, action='append',
                        metavar='PROJECT=BRANCH', help='IGNORED')
    for zuul_suffix in ZUUL_ENV_SUFFIXES:
        env_name = 'ZUUL_%s' % zuul_suffix.upper()
        parser.add_argument(
            '--zuul-%s' % zuul_suffix, metavar='$' + env_name,
            help='IGNORED'
        )

    # Active arguments
    parser.add_argument('-m', '--map', dest='clone_map_file',
                        help='specify clone map file')
    parser.add_argument('-v', '--verbose', dest='verbose',
                        action='store_true', help='verbose output')
    parser.add_argument('--workspace', dest='workspace',
                        default=os.getcwd(),
                        help='where to clone repositories too')
    parser.add_argument('projects', nargs='+',
                        help='list of Gerrit projects to clone')

    return parser.parse_args()

def main():
    args = parse_args()

    for project in args.projects:
        src = os.path.join(REPO_SRC_DIR, project)
        dst = os.path.join(args.workspace, project)
        #shutil.copytree(src, dst)
        cmd = "shutil.copytree(%s, %s)" % (src, dst)
        print("%s" % cmd)

if __name__ == "__main__":
    main()
