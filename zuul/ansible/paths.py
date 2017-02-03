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

import os

# NOTE(mordred) This is still not safe, because if the chdir task parameter
# So we need to actually get config in here from the launcher, since the
# launcher dir is the thing we want to consider the "safe" location


def _is_safe_path(path):
    if os.path.isabs(path):
        return False
    if not os.path.abspath(os.path.expanduser(path)).startswith(
            os.path.abspath(os.path.curdir)):
        return False
    return True
