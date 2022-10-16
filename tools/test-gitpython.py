# Copyright 2022 Acme Gating, LLC
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

from collections import defaultdict
import os
import shutil

import git
import gitdb

from time import perf_counter
from contextlib import contextmanager

PROJECT = 'zuul/zuul'
TESTREF = 'refs/changes/76/861376/1:refs/zuul/fetch'
#
TESTREPO = f'https://opendev.org/{PROJECT}'
FETCHURL = f'https://review.opendev.org/{PROJECT}'
TESTDIR = "/tmp/testgit"

TIMES = defaultdict(list)


@contextmanager
def timer(msg):
    start = perf_counter()
    yield
    elapsed = perf_counter() - start
    TIMES[msg].append(elapsed)
    print(msg, elapsed)


def setup():
    shutil.rmtree(TESTDIR, ignore_errors=True)
    with timer('Clone'):
        mygit = git.cmd.Git(os.getcwd())
        mygit.clone(TESTREPO, TESTDIR)


def test():
    with timer('Check repo'):
        repo = git.Repo(TESTDIR)
    with timer('For each ref'):
        refs = repo.git.for_each_ref('--format=%(objectname) %(refname)')
        refs = [x.split(' ') for x in refs.splitlines()]
        refs = [x for x in refs if len(x) == 2]
        print("Number of refs:", len(refs))
    with timer('Set each ref'):
        for hexsha, path in refs:
            path += '_test'
            binsha = gitdb.util.to_bin_sha(hexsha)
            obj = git.objects.Object.new_from_sha(repo, binsha)
            git.refs.Reference.create(repo, path, obj, force=True)
    with timer('Delete each ref'):
        for hexsha, path in refs:
            path += '_test'
            git.refs.SymbolicReference.delete(repo, path)
    with timer('Checkout a ref'):
        hexsha, path = refs[0]
        repo.head.reference = path
        repo.head.reset(working_tree=True)
        # repo.git.clean('-x', '-f', '-d')
        repo.git.checkout(path)
    with timer('Checkout master'):
        path = 'origin/master'
        repo.head.reference = path
        repo.head.reset(working_tree=True)
        # repo.git.clean('-x', '-f', '-d')
        repo.git.checkout(path)
    with timer('Fetch'):
        repo.git.fetch(FETCHURL, TESTREF)
    with timer('Merge'):
        repo.git.merge('FETCH_HEAD')
    with timer('Checkout master'):
        path = 'origin/master'
        repo.head.reference = path
        repo.head.reset(working_tree=True)
        # repo.git.clean('-x', '-f', '-d')
        repo.git.checkout(path)
    with timer('Cherry-pick'):
        repo.git.cherry_pick('FETCH_HEAD')


setup()
for x in range(10):
    test()


print("")
print("Summary")


for msg, times in TIMES.items():
    print(msg, sum(times) / len(times))
