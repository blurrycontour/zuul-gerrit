# Copyright 2015 Red Hat, Inc.
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

"""
This module defines classes used in matching changes based on job
configuration.
"""

import abc
import re


class AbstractChangeMatcher(object):

    def __init__(self, regex):
        self._regex = regex
        self.regex = re.compile(regex)

    @abc.abstractmethod
    def matches(self, change):
        """Return a boolean indication of whether change matches
        implementation-specific criteria.
        """
        raise NotImplementedError()

    def copy(self):
        return self.__class__(self._regex)

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return '{%s:%s}' % (self.__class__.__name__, self._regex)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self._regex)


class ProjectMatcher(AbstractChangeMatcher):

    def matches(self, change):
        return self.regex.match(str(change.project))


class FileMatcher(AbstractChangeMatcher):

    def matches(self, change):
        if not hasattr(change, 'files'):
            return False
        for file_ in change.files:
            if self.regex.match(file_):
                return True
        return False


class AbstractMatcherCollection(AbstractChangeMatcher):

    def __init__(self, matchers):
        self.matchers = matchers

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return '{%s:%s}' % (self.__class__.__name__,
                            ','.join([str(x) for x in self.matchers]))

    def __repr__(self):
        return '<%s>' % self.__class__.__name__

    def copy(self):
        return self.__class__(self.matchers[:])


class MatchAllFiles(AbstractMatcherCollection):

    commit_regex = re.compile('^/COMMIT_MSG$')

    def __init__(self, matchers):
        self.matchers = matchers

    def matches(self, change):
        if not (hasattr(change, 'files') and change.files):
            return False
        for file_ in change.files:
            matched_file = False
            for matcher in self.matchers:
                if matcher.regex.match(file_):
                    matched_file = True
                    break
            if self.commit_regex.match(file_):
                matched_file = True
            if not matched_file:
                return False
        return True


class MatchOnAll(AbstractMatcherCollection):

    def matches(self, change):
        for matcher in self.matchers:
            if not matcher.matches(change):
                return False
        return True


class MatchOnAny(AbstractMatcherCollection):

    def matches(self, change):
        for matcher in self.matchers:
            if matcher.matches(change):
                return True
        return False
