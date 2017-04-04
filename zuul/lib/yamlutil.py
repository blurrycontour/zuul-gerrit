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
import yaml
from yaml import YAMLObject, YAMLError  # noqa: F401

try:
    from yaml import cyaml
    import _yaml
    SafeLoader = cyaml.CSafeLoader
    SafeDumper = cyaml.CSafeDumper
    Mark = _yaml.Mark
except ImportError:
    SafeLoader = yaml.SafeLoader
    SafeDumper = yaml.SafeDumper
    Mark = yaml.Mark


def safe_load(stream, *args, **kwargs):
    return yaml.load(stream, *args, **kwargs, Loader=SafeLoader)


def safe_dump(stream, *args, **kwargs):
    return yaml.dump(stream, *args, **kwargs, Dumper=SafeDumper)
