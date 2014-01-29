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
import logging
import os
import re
import sys
import yaml
from git import GitCommandError
from zuul.merger.merger import Repo

ZUUL_ENV_SUFFIXES = (
    'branch',
    'change',
    'patchset',
    'pipeline',
    'project',
    'ref',
    'url',
)


class Cloner(object):
    log = logging.getLogger("zuul.Cloner")

    def __init__(self, args):
        self.args = args
        self.clone_map = []
        self.dests = None

        self.setup_logging()
        if self.args.clone_map_file:
            self.read_clone_map()

    def setup_logging(self):
        if self.args.verbose:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)

    def read_clone_map(self):
        clone_map_file = os.path.expanduser(self.args.clone_map_file)
        if not os.path.exists(clone_map_file):
            raise Exception("Unable to read clone map file at %s." %
                            clone_map_file)
        clone_map_file = open(self.args.clone_map_file)
        self.clone_map = yaml.load(clone_map_file).get('clonemap')
        self.log.info("Loaded map containing %s rules" % len(self.clone_map))
        return self.clone_map

    def execute(self):
        mapper = CloneMapper(self.clone_map, self.args.projects)
        dests = mapper.expand(workspace=self.args.workspace)

        for project, dest in dests.iteritems():
            self.prepare_repo(project, dest)

    def prepare_repo(self, project, dest):
        """Clone a repository for project at dest and apply a reference
        suitable for testing. The reference lookup is attempted in that order:
        - Zuul reference for the indicated branch
        - Zuul reference for the master branch
        - The tip of the indicated branch
        - The tip of the master branch
        """

        git_remote = '%s/%s' % (self.args.zuul_url, project),
        self.log.info("Creating repo for %s using %s"
                      % (project, git_remote))
        repo = Repo(
            remote=git_remote,
            local=dest,
            email=None,
            username=None)
        if not repo._initialized:
            raise Exception("Error cloning %s to %s" % (git_remote, dest))

        # Lot of debug messages to give folks clue when using --verbose
        try:
            ref = repo.fetch(self.args.zuul_ref)
            self.log.debug("Project %s has %s" % (project, ref))
        except GitCommandError:
            self.log.debug("Project %s MISSES %s"
                           % (project, self.args.zuul_ref))
            pass

        if repo.getBranchHead(self.args.zuul_branch):
            self.log.debug("Project %s has branch %s"
                           % (project, self.args.zuul_branch))
            ref = self.args.zuul_branch
        else:
            self.log.debug("Project %s missing branch %s."
                           "Falling back to master"
                           % (project, self.args.zuul_branch))
            ref = 'master'
        self.log.info("Project %s will use ref %s" % (project, ref))

        repo.checkout(ref)


class CloneMapper(object):
    log = logging.getLogger("zuul.CloneMapper")

    def __init__(self, clonemap, projects):
        self.clonemap = clonemap
        self.projects = projects

    def expand(self, workspace):
        self.log.info("Workspace path set to: %s" % workspace)

        is_valid = True
        ret = {}
        for project in self.projects:
            dests = []
            for mapping in self.clonemap:
                if re.match(r'^%s$' % mapping['name'],
                            project):
                    # Might be matched more than one time
                    dests.append(
                        re.sub(mapping['name'], mapping['dest'], project))

            if len(dests) > 1:
                self.log.error("Duplicate destinations for %s: %s."
                               % (project, dests))
                is_valid = False
            elif len(dests) == 0:
                self.log.debug("Using %s as destination (unmatched)"
                               % project)
                ret[project] = [project]
            else:
                ret[project] = dests

        if not is_valid:
            raise Exception("Expansion error. Check error messages above")

        self.log.info("Applying workspace to destination...")
        for project, dest in sorted(ret.iteritems()):
            dest = os.path.normpath(os.path.join(workspace, dest[0]))
            ret[project] = dest
            self.log.info("  %s -> %s" % (project, dest))

        self.log.info("Expansion completed.")
        return ret


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
