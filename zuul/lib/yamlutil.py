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
import types
import yaml
from yaml import (  # noqa: F401
    YAMLObject, YAMLError, ScalarNode, MappingNode, SequenceNode
)

try:
    # Explicit type ignore to deal with provisional import failure
    # Details at https://github.com/python/mypy/issues/1153
    from yaml import cyaml  # type: ignore
    import _yaml
    SafeLoader = cyaml.CSafeLoader
    SafeDumper = cyaml.CSafeDumper
    Mark = _yaml.Mark
except ImportError:
    SafeLoader = yaml.SafeLoader  # type: ignore
    SafeDumper = yaml.SafeDumper  # type: ignore
    Mark = yaml.Mark


yaml.add_representer(types.MappingProxyType,
                     yaml.representer.SafeRepresenter.represent_dict,
                     Dumper=SafeDumper)


def safe_load(stream, *args, **kwargs):
    return yaml.load(stream, *args, Loader=SafeLoader, **kwargs)


def safe_dump(data, *args, **kwargs):
    return yaml.dump(data, *args, Dumper=SafeDumper, **kwargs)
