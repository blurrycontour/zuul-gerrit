# Copyright 2024 Acme Gating, LLC
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

# Copyright 2018-2019 Red Hat, Inc.
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

import voluptuous as vs


artifact = {
    vs.Required('name'): str,
    vs.Required('url'): str,
    'metadata': dict,
}

artifact_data = {
    'zuul': {
        'log_url': str,
        'artifacts': [artifact],
        vs.Extra: object,
    },
    vs.Extra: object,
}

warning_data = {
    'zuul': {
        'log_url': str,
        'warnings': [str],
        vs.Extra: object,
    },
    vs.Extra: object,
}

artifact_schema = vs.Schema(artifact_data)
warning_schema = vs.Schema(warning_data)
