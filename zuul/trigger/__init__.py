# Copyright 2014 Rackspace Australia
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


class BaseTrigger(object):
    """Base class for triggers.

    Defines the exact public methods that must be supplied."""
    def __init__(self, *args, **kwargs):
        raise NotImplementedError()

    def stop(self):
        raise NotImplementedError()

    def getEventFilters(self, trigger_conf):
        raise NotImplementedError()

    def postConfig(self):
        raise NotImplementedError()

    def onChangeMerged(self, change):
        raise NotImplementedError()

    def onChangeEnqueued(self, change, pipeline):
        raise NotImplementedError()
