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

from zuul import model

import voluptuous as vs


class BaseProviderImage(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.name = config['name']


class BaseProviderFlavor(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.name = config['name']


class BaseProviderLabel(metaclass=abc.ABCMeta):
    def __init__(self, config):
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


class BaseProvider(metaclass=abc.ABCMeta):
    """Base class for provider."""

    def __init__(self, driver, connection, canonical_name, config):
        self.driver = driver
        self.connection = connection

        self.canonical_name = canonical_name
        self.name = config['name']
        self.section_name = config['section']
        self.description = config.get('description')

        self.labels = self.parseLabels(config)

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
    def getEndpoint(self):
        """Get an endpoint for this provider"""
        pass


class BaseProviderSchema(metaclass=abc.ABCMeta):
    def getLabelSchema(self):
        schema = vs.Schema({
            vs.Required('name'): str,
            'description': str,
            'image': str,
            'flavor': str,
        })
        return schema

    def getImageSchema(self):
        schema = vs.Schema({
            vs.Required('name'): str,
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
