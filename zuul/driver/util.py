# Copyright 2017 Red Hat, Inc.
# Copyright 2023 Acme Gating, LLC
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

# Utility methods to promote consistent configuration among drivers.

import datetime

import voluptuous as vs

from zuul.configloader import ZUUL_REGEX, make_regex  # noqa


class TimeOffset:
    weekday_offsets = (3, 1, 1, 1, 1, 1, 2)

    def __init__(self, value):
        """Creates a dynamic time offset from the current time.  To test if
        some value is newer than 2 days ago, use:

            value > TimeOffset('2d')

        This class compares with datetime instances.
        """

        self.seconds = None
        self.weekdays = None
        if value.endswith('weekdays'):
            self.weekdays = int(value[:-len('weekdays')])
        elif value.endswith('weekday'):
            self.weekdays = int(value[:-len('weekday')])
        elif value.endswith('s'):
            self.seconds = int(value[:-1])
        elif value.endswith('m'):
            self.seconds = int(value[:-1]) * 60
        elif value.endswith('h'):
            self.seconds = int(value[:-1]) * 60 * 60
        elif value.endswith('d'):
            self.seconds = int(value[:-1]) * 24 * 60 * 60
        elif value.endswith('w'):
            self.seconds = int(value[:-1]) * 7 * 24 * 60 * 60
        else:
            raise Exception("Unable to parse time value: %s" % value)

    def _getPointInTime(self):
        now = datetime.datetime.utcnow()
        point = now
        if self.weekdays is not None:
            for x in range(self.weekdays):
                point -= datetime.timedelta(
                    days=self.weekday_offsets[point.weekday()])
        else:
            point -= datetime.timedelta(seconds=self.seconds)
        return point

    def __gt__(self, other):
        return self._getPointInTime() > other

    def __lt__(self, other):
        return self._getPointInTime() < other

    def __le__(self, other):
        return self._getPointInTime() <= other

    def __ge__(self, other):
        return self._getPointInTime() >= other

    def __eq__(self, other):
        return self._getPointInTime() == other

    def __ne__(self, other):
        return self._getPointInTime() != other


def scalar_or_list(x):
    return vs.Any([x], x)


def to_list(item):
    if not item:
        return []
    if isinstance(item, list):
        return item
    return [item]
