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

import abc
import json
import urllib.parse

from zuul import model
from zuul.zk import zkobject

import voluptuous as vs


class BaseProviderImage(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.project_canonical_name = config['project_canonical_name']
        self.name = config['name']
        self.branch = config['branch']
        self.type = config['type']
        # TODO: get formats from configuration
        self.formats = set(['raw'])

    @property
    def canonical_name(self):
        return '/'.join([
            urllib.parse.quote_plus(
                self.project_canonical_name),
            urllib.parse.quote_plus(self.name),
        ])


class BaseProviderFlavor(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.project_canonical_name = config['project_canonical_name']
        self.name = config['name']


class BaseProviderLabel(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.project_canonical_name = config['project_canonical_name']
        self.name = config['name']
        self.min_ready = config.get('min-ready', 0)


class BaseProviderEndpoint(metaclass=abc.ABCMeta):
    """Base class for provider endpoints.

    Providers and Sections are combined to describe clouds, and they
    may not correspond exactly with the cloud's topology.  To
    reconcile this, the Endpoint class is used for storing information
    about what we would typically call a region of a cloud.  This is
    the unit of visibility of instances, VPCs, images, etc.
    """

    def __init__(self, driver, connection):
        self.driver = driver
        self.connection = connection


class BaseProvider(zkobject.PolymorphicZKObjectMixin,
                   zkobject.ShardedZKObject):
    """Base class for provider."""

    def __init__(self, *args):
        super().__init__()
        if args:
            (driver, connection, tenant_name, canonical_name, config) = args
            config = config.copy()
            config.pop('_source_context')
            config.pop('_start_mark')
            self._set(
                driver=driver,
                connection=connection,
                connection_name=connection.connection_name,
                tenant_name=tenant_name,
                canonical_name=canonical_name,
                config=config,
                **self.parseConfig(config),
            )

    @classmethod
    def fromZK(cls, context, path, connections):
        """Deserialize a Provider (subclass) from ZK.

        To deserialize a Provider from ZK, pass the connection
        registry as the "connections" argument.

        The Provider subclass will automatically be deserialized and
        the connection/driver attributes updated from the connection
        registry.

        """
        raw_data, zstat = cls._loadData(context, path)
        obj = cls._fromRaw(raw_data, zstat)
        connection = connections.connections[obj.connection_name]
        obj._set(connection=connection,
                 driver=connection.driver)
        return obj

    def parseConfig(self, config):
        return dict(
            name=config['name'],
            section_name=config['section'],
            description=config.get('description'),
            images=self.parseImages(config),
            labels=self.parseLabels(config),
        )

    def deserialize(self, raw, context):
        data = super().deserialize(raw, context)
        data.update(self.parseConfig(data['config']))
        return data

    def serialize(self, context):
        data = dict(
            tenant_name=self.tenant_name,
            canonical_name=self.canonical_name,
            config=self.config,
            connection_name=self.connection.connection_name,
        )
        return json.dumps(data, sort_keys=True).encode("utf8")

    @property
    def tenant_scoped_name(self):
        return f'{self.tenant_name}-{self.name}'

    def parseImages(self, config):
        images = []
        for image_config in config.get('images', []):
            images.append(self.parseImage(image_config))
        return images

    def parseLabels(self, config):
        labels = []
        for label_config in config.get('labels', []):
            labels.append(self.parseLabel(label_config))
        return labels

    @abc.abstractmethod
    def parseLabel(self, label_config):
        """Instantiate a ProviderLabel subclass

        :returns: a ProviderLabel subclass
        :rtype: ProviderLabel
        """
        pass

    @abc.abstractmethod
    def parseImage(self, image_config):
        """Instantiate a ProviderImage subclass

        :returns: a ProviderImage subclass
        :rtype: ProviderImage
        """
        pass

    @abc.abstractmethod
    def getEndpoint(self):
        """Get an endpoint for this provider"""
        pass

    def getPath(self):
        path = (f'/zuul/tenant/{self.tenant_name}'
                f'/provider/{self.canonical_name}/config')
        return path

    def hasLabel(self, label):
        return any(lbl.name == label for lbl in self.labels)


class BaseProviderSchema(metaclass=abc.ABCMeta):
    def getLabelSchema(self):
        schema = vs.Schema({
            vs.Required('project_canonical_name'): str,
            vs.Required('name'): str,
            'description': str,
            'image': str,
            'flavor': str,
        })
        return schema

    def getImageSchema(self):
        schema = vs.Schema({
            vs.Required('project_canonical_name'): str,
            vs.Required('name'): str,
            vs.Required('branch'): str,
            'description': str,
            'username': str,
            'connection-type': str,
            'connection-port': int,
            'python-path': str,
            'shell-type': str,
            'type': str,
        })
        return schema

    def getFlavorSchema(self):
        schema = vs.Schema({
            vs.Required('project_canonical_name'): str,
            vs.Required('name'): str,
            'description': str,
        })
        return schema

    def getProviderSchema(self):
        schema = vs.Schema({
            '_source_context': model.SourceContext,
            '_start_mark': model.ZuulMark,
            vs.Required('name'): str,
            vs.Required('section'): str,
            vs.Required('labels'): [self.getLabelSchema()],
            vs.Required('images'): [self.getImageSchema()],
            vs.Required('flavors'): [self.getFlavorSchema()],
            'abstract': bool,
            'parent': str,
            'connection': str,
            'boot-timeout': int,
            'launch-timeout': int,
        })
        return schema
