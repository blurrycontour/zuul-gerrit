# Copyright 2017 Red Hat, Inc.
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


from zuul.ansible import paths
csvfile = paths._import_ansible_lookup_plugin("csvfile")


class LookupModule(csvfile.LookupModule):

    def read_csv(self, filename, *args, **kwargs):
        if not paths._is_safe_path(filename):
            return paths._fail_dict(filename)
        return super(LookupModule, self).read_csv(filename, *args, **kwargs)
