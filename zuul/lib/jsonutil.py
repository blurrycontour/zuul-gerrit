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
import logging
import types
try:
    import orjson
except ImportError:
    orjson = None

import zuul.model

LOGGER = logging.getLogger(__name__)


class ZuulJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            return self._default(obj)
        except TypeError:
            return json.JSONEncoder.default(self, obj)

    @classmethod
    def _default(cls, obj):
        if isinstance(obj, types.MappingProxyType):
            d = dict(obj)
            # Always remove SafeLoader left-over
            d.pop('_source_context', None)
            d.pop('_start_mark', None)
            return d
        elif (
                isinstance(obj, zuul.model.SourceContext) or
                isinstance(obj, zuul.model.ZuulMark)):
            return {}
        raise TypeError


def json_dumps(obj, **kw):
    return json.dumps(obj, cls=ZuulJSONEncoder, **kw)


def json_dumpb(obj, sort_keys=False):
    if orjson:
        option = orjson.OPT_SORT_KEYS if sort_keys else None
        return orjson.dumps(obj, default=ZuulJSONEncoder._default,
                            option=option)
    return json_dumps(obj, sort_keys=sort_keys).encode("utf8")


def json_loadb(data):
    if orjson:
        return orjson.loads(data)
    else:
        return json.loads(data)
