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

import json
import types

import msgspec


class JSONDecodeError(ValueError):
    pass


class ZuulJSONEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            _zuul_encoder(o)
        except NotImplementedError:
            return json.JSONEncoder.default(self, o)


def _zuul_encoder(o):
    # Local import to avoid circular import issues with zuul.module
    from zuul.model import SourceContext, ZuulMark
    if isinstance(o, types.MappingProxyType):
        d = dict(o)
        # Always remove SafeLoader left-over
        d.pop('_source_context', None)
        d.pop('_start_mark', None)
        return d
    elif (isinstance(o, SourceContext) or isinstance(o, ZuulMark)):
        return {}
    elif isinstance(o, str):
        return str(o)
    elif isinstance(o, int):
        return int(o)
    raise NotImplementedError(type(o))


_default_encoder = msgspec.json.Encoder(
    decimal_format="number",
    enc_hook=_zuul_encoder
)

_deterministic_encoder = msgspec.json.Encoder(
    order="deterministic",
    decimal_format="number",
    enc_hook=_zuul_encoder
)


def json_dumpb(obj, sort_keys=False):
    if sort_keys:
        return _deterministic_encoder.encode(obj)
    else:
        return _default_encoder.encode(obj)


def json_loadb(data):
    try:
        return msgspec.json.decode(data)
    except msgspec.DecodeError as exc:
        raise JSONDecodeError from exc
