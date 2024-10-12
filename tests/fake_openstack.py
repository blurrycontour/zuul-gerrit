# Copyright (C) 2011-2013 OpenStack Foundation
# Copyright 2022, 2024 Acme Gating, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import uuid

from zuul.driver.openstack.openstackendpoint import OpenstackProviderEndpoint


class FakeOpenstackObject:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__kw = list(kw.keys())

    def _get_dict(self):
        data = {}
        for k in self.__kw:
            data[k] = getattr(self, k)
        return data

    def __contains__(self, key):
        return key in self.__dict__

    def __getitem__(self, key, default=None):
        return getattr(self, key, default)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


class FakeOpenstackFlavor(FakeOpenstackObject):
    pass


class FakeOpenstackServer(FakeOpenstackObject):
    pass


class FakeOpenstackLocation(FakeOpenstackObject):
    pass


class FakeOpenstackImage(FakeOpenstackObject):
    pass


class FakeOpenstackCloud:
    log = logging.getLogger("zuul.FakeOpenstackCloud")

    def __init__(self):
        self.servers = []
        self.volumes = []
        self.images = []
        self.flavors = [
            FakeOpenstackFlavor(
                id='425e3203150e43d6b22792f86752533d',
                name='Fake Flavor',
                ram=8192,
                vcpus=4,
            )
        ]

    def _getConnection(self):
        return FakeOpenstackConnection(self)


class FakeOpenstackResponse:
    def __init__(self, data):
        self._data = data
        self.links = []

    def json(self):
        return self._data


class FakeOpenstackSession:
    def __init__(self, cloud):
        self.cloud = cloud

    def get(self, uri, headers, params):
        if uri == '/servers/detail':
            server_list = []
            for server in self.cloud.servers:
                data = server._get_dict()
                data['hostId'] = data.pop('host_id')
                data['OS-EXT-AZ:availability_zone'] = data.pop('location').zone
                data['os-extended-volumes:volumes_attached'] =\
                    data.pop('volumes')
                server_list.append(data)
            return FakeOpenstackResponse({'servers': server_list})


class FakeOpenstackConfig:
    pass


class FakeOpenstackConnection:
    log = logging.getLogger("zuul.FakeOpenstackConnection")

    def __init__(self, cloud):
        self.cloud = cloud
        self.compute = FakeOpenstackSession(cloud)
        self.config = FakeOpenstackConfig()
        self.config.config = {}
        self.config.config['image_format'] = 'qcow2'

    def list_flavors(self, get_extra=False):
        return self.cloud.flavors

    def list_volumes(self):
        return self.cloud.volumes

    def list_servers(self):
        return self.cloud.servers

    def create_server(self, wait=None, name=None, image=None,
                      flavor=None, config_drive=None, key_name=None,
                      meta=None):
        location = FakeOpenstackLocation(zone=None)
        server = FakeOpenstackServer(
            id=uuid.uuid4().hex,
            name=name,
            host_id='fake_host_id',
            location=location,
            volumes=[],
            status='ACTIVE',
            addresses=dict(
                public=[dict(version=4, addr='fake'),
                        dict(version=6, addr='fake_v6')],
                private=[dict(version=4, addr='fake')]
            )
        )
        self.cloud.servers.append(server)
        return server

    def delete_server(self, name_or_id):
        for x in self.cloud.servers:
            if x.id == name_or_id:
                self.cloud.servers.remove(x)
                return

    def create_image(self, wait=None, name=None, filename=None,
                     is_public=None, md5=None, sha256=None,
                     timeout=None, **meta):
        image = FakeOpenstackImage(
            id=uuid.uuid4().hex,
            name=name,
            filename=filename,
            is_public=is_public,
            md5=md5,
            sha256=sha256,
            status='ACTIVE',
        )
        self.cloud.images.append(image)
        return image

    def delete_image(self, name_or_id):
        for x in self.cloud.servers:
            if x.id == name_or_id:
                self.cloud.servers.remove(x)
                return


class FakeOpenstackProviderEndpoint(OpenstackProviderEndpoint):
    def _getClient(self):
        return self._fake_cloud._getConnection()

    def _expandServer(self, server):
        return server
