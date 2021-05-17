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
import base64
import types

from zuul.lib import encryption

import yaml
from yaml import YAMLError  # noqa: F401


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


class EncryptedPKCS1_OAEP:
    yaml_tag = u'!encrypted/pkcs1-oaep'

    def __init__(self, ciphertext):
        if isinstance(ciphertext, list):
            self.ciphertext = [base64.b64decode(x.value)
                               for x in ciphertext]
        else:
            self.ciphertext = base64.b64decode(ciphertext)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, EncryptedPKCS1_OAEP):
            return False
        return (self.ciphertext == other.ciphertext)

    @classmethod
    def from_yaml(cls, loader, node):
        return cls(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        ciphertext = data.ciphertext
        if isinstance(ciphertext, list):
            ciphertext = [yaml.ScalarNode(tag='tag:yaml.org,2002:str',
                                          value=base64.b64encode(x))
                          for x in ciphertext]
            return yaml.SequenceNode(tag=cls.yaml_tag,
                                     value=ciphertext)
        ciphertext = base64.b64encode(ciphertext).decode('utf8')
        return yaml.ScalarNode(tag=cls.yaml_tag, value=ciphertext)

    def decrypt(self, private_key):
        if isinstance(self.ciphertext, list):
            return ''.join([
                encryption.decrypt_pkcs1_oaep(chunk, private_key).
                decode('utf8')
                for chunk in self.ciphertext])
        else:
            return encryption.decrypt_pkcs1_oaep(self.ciphertext,
                                                 private_key).decode('utf8')


def safe_load(stream, *args, **kwargs):
    return yaml.load(stream, *args, Loader=SafeLoader, **kwargs)


def safe_dump(stream, *args, **kwargs):
    return yaml.dump(stream, *args, Dumper=SafeDumper, **kwargs)


class EncryptedDumper(SafeDumper):
    pass


class EncryptedLoader(SafeLoader):
    pass


# Add support for encrypted objects
EncryptedDumper.add_representer(EncryptedPKCS1_OAEP,
                                EncryptedPKCS1_OAEP.to_yaml)
EncryptedLoader.add_constructor(EncryptedPKCS1_OAEP.yaml_tag,
                                EncryptedPKCS1_OAEP.from_yaml)
# Also add support for serializing frozen data
EncryptedDumper.add_representer(
    types.MappingProxyType,
    yaml.representer.SafeRepresenter.represent_dict)


def encrypted_dump(data, *args, **kwargs):
    return yaml.dump(data, *args, Dumper=EncryptedDumper, **kwargs)


def encrypted_load(stream, *args, **kwargs):
    return yaml.load(stream, *args, Loader=EncryptedLoader, **kwargs)
