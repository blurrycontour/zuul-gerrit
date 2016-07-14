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
import gear

class GearJobWrapper(object):
    """A wrapper that eases encode/decode for gear.Job"""

    @staticmethod
    def _encode_data(value, none_ok=False):
        if value is not None or none_ok is False:
            try:
                value = value.encode('utf-8')
            except AttributeError:
                raise ValueError('Expected value to be str but got %s '
                                 'instead' % type(value))
        return value

    @staticmethod
    def _decode_data(value, none_ok=False):
        if value is not None or none_ok is False:
            value = value.decode('utf-8')
        return value

    @staticmethod
    def gear_job(name, arguments, unique=None, cls=gear.Job):
        # Helper function to make creating a gear job with
        # encodings isolated code.
        return cls(
            GearJobWrapper._encode_data(name),
            GearJobWrapper._encode_data(arguments),
            GearJobWrapper._encode_data(unique, none_ok=True))

    def __init__(self, job):
            self.job = job

    def sendWorkData(self, data):
        self.job.sendWorkData(GearJobWrapper._encode_data(data))

    def sendWorkException(self, data=None):
        self.job.sendWorkException(GearJobWrapper._encode_data(data),
                                   none_ok=True)

    def sendWorkComplete(self, data=None):
        self.job.sendWorkComplete(GearJobWrapper._encode_data(data),
                                   none_ok=True)

    def __getattr__(self, item):
        return getattr(self.job, item)

    @property
    def name(self):
        return self._decode_data(self.job.name)

    @property
    def unique(self):
        return self._decode_data(self.job.unique, none_ok=True)

    @property
    def data(self):
        return self._decode_data(self.job.data)

    @property
    def arguments(self):
        return GearJobWrapper._decode_data(self.job.arguments)