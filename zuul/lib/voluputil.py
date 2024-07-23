# Copyright 2024 Acme Gating, LLC
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

# This adds some helpers that are useful for mutating hyphenated YAML
# structures into underscored python dicts.

import voluptuous as vs


UNDEFINED = object()


class Required(vs.Required):
    def __init__(self, schema, default=UNDEFINED, output=None):
        super().__init__(schema, default=default)
        if output is None:
            output = str(schema).replace('-', '_').lower()
        self.output = output

    def __call__(self, data):
        # Superclass ensures that data==schema
        super().__call__(data)
        # Return our mutated form
        return self.output


class Optional(vs.Optional):
    def __init__(self, schema, default=UNDEFINED, output=None):
        super().__init__(schema, default=default)
        if output is None:
            output = str(schema).replace('-', '_').lower()
        self.output = output

    def __call__(self, data):
        # Superclass ensures that data==schema
        super().__call__(data)
        # Return our mutated form
        return self.output


class Nullable:
    def __init__(self, schema):
        self.schema = vs.Schema(schema)

    def __call__(self, v):
        if v is UNDEFINED:
            return None
        return self.schema(v)
