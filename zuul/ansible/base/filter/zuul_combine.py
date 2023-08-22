# Copyright 2023 Acme Gating, LLC
#
# Zuul is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Zuul is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from ansible.template import recursive_check_defined


def zuul_combine(old, new):
    ret = old.copy()
    for key in new:
        try:
            recursive_check_defined(new[key])
            ret[key] = new[key]
        except Exception:
            pass
    return ret


class FilterModule:

    def filters(self):
        return {
            'zuul_combine': zuul_combine,
        }
