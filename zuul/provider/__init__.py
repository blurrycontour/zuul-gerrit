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
import math
import urllib.parse

from zuul.lib.voluputil import Required, Optional, Nullable, assemble
from zuul import model
from zuul.driver.util import QuotaInformation
from zuul.zk import zkobject
import zuul.provider.schema as provider_schema

import voluptuous as vs


class BaseProviderImage(metaclass=abc.ABCMeta):
    inheritable_schema = assemble(
        provider_schema.common_image,
    )
    schema = assemble(
        provider_schema.common_image,
        provider_schema.base_image,
    )

    def __init__(self, config):
        self.__dict__.update(self.schema(config))
        # TODO: generate this automatically from config
        self.formats = set(['raw'])

    @property
    def canonical_name(self):
        return '/'.join([
            urllib.parse.quote_plus(
                self.project_canonical_name),
            urllib.parse.quote_plus(self.name),
        ])


class BaseProviderFlavor(metaclass=abc.ABCMeta):
    inheritable_schema = assemble()
    schema = assemble(
        provider_schema.base_flavor,
    )

    def __init__(self, config):
        self.__dict__.update(self.schema(config))


class BaseProviderLabel(metaclass=abc.ABCMeta):
    inheritable_schema = assemble()
    schema = assemble(
        provider_schema.base_label,
    )

    def __init__(self, config):
        self.__dict__.update(self.schema(config))


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


class BaseProviderSchema(metaclass=abc.ABCMeta):
    def getLabelSchema(self):
        return BaseProviderLabel.schema

    def getImageSchema(self):
        return BaseProviderImage.schema

    def getFlavorSchema(self):
        return BaseProviderFlavor.schema

    def getProviderSchema(self):
        schema = vs.Schema({
            '_source_context': model.SourceContext,
            '_start_mark': model.ZuulMark,
            Required('name'): str,
            Required('section'): str,
            Required('labels'): [self.getLabelSchema()],
            Required('images'): [self.getImageSchema()],
            Required('flavors'): [self.getFlavorSchema()],
            Required('abstract'): vs.Maybe(bool),
            Required('parent'): vs.Maybe(str),
            Required('connection'): str,
            Optional('boot-timeout'): Nullable(int),
            Optional('launch-timeout'): Nullable(int),
        })
        return schema


class BaseProvider(zkobject.PolymorphicZKObjectMixin,
                   zkobject.ShardedZKObject):
    """Base class for provider."""
    schema = BaseProviderSchema().getProviderSchema()

    def __init__(self, *args):
        super().__init__()
        if args:
            (driver, connection, tenant_name, canonical_name, config) = args
            config = config.copy()
            config.pop('_source_context')
            config.pop('_start_mark')
            parsed_config = self.parseConfig(config)
            parsed_config.pop('connection')
            self._set(
                driver=driver,
                connection=connection,
                connection_name=connection.connection_name,
                tenant_name=tenant_name,
                canonical_name=canonical_name,
                config=config,
                **parsed_config,
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

    def getProviderSchema(self):
        return self.schema

    def parseConfig(self, config):
        schema = self.getProviderSchema()
        ret = schema(config)
        ret.update(dict(
            images=self.parseImages(config),
            flavors=self.parseFlavors(config),
            labels=self.parseLabels(config),
        ))
        return ret

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
        images = {}
        for image_config in config.get('images', []):
            i = self.parseImage(image_config)
            images[i.name] = i
        return images

    def parseFlavors(self, config):
        flavors = {}
        for flavor_config in config.get('flavors', []):
            f = self.parseFlavor(flavor_config)
            flavors[f.name] = f
        return flavors

    def parseLabels(self, config):
        labels = {}
        for label_config in config.get('labels', []):
            l = self.parseLabel(label_config)
            labels[l.name] = l
        return labels

    @abc.abstractmethod
    def parseLabel(self, label_config):
        """Instantiate a ProviderLabel subclass

        :returns: a ProviderLabel subclass
        :rtype: ProviderLabel
        """
        pass

    @abc.abstractmethod
    def parseFlavor(self, flavor_config):
        """Instantiate a ProviderFlavor subclass

        :returns: a ProviderFlavor subclass
        :rtype: ProviderFlavor
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
        return label in self.labels

    def getNodeTags(self, system_id, request, provider, label,
                    node_uuid):
        """Return the tags that should be stored with the node

        :param str system_id: The Zuul system uuid
        :param NodesetRequest request: The node request
        :param Provider provider: The cloud provider
        :param ProviderLabel label: The node label
        :param str node_uuid: The node uuid
        """
        tags = dict()

        # TODO: add other potentially useful attrs from nodepool
        attributes = model.Attributes(
            request_id=request.uuid,
            tenant_name=provider.tenant_name,
        )
        for k, v in label.tags.items():
            try:
                tags[k] = v.format(**attributes)
            except Exception:
                self.log.exception("Error formatting metadata %s", k)

        fixed = {
            'zuul_system_id': system_id,
            'zuul_provider_name': self.tenant_scoped_name,
            'zuul_provider_cname': self.canonical_name,
            'zuul_node_uuid': node_uuid,
        }
        tags.update(fixed)
        return tags

    def getCreateStateMachine(self, node,
                              image_external_id,
                              log):
        """Return a state machine suitable for creating an instance

        This method should return a new state machine object
        initialized to create the described node.

        :param ProviderNode node: The node object.
        :param ProviderLabel label: A config object representing the
            provider-label for the node.
        :param str image_external_id: If provided, the external id of
            a previously uploaded image; if None, then the adapter should
            look up a cloud image based on the label.
        :param log Logger: A logger instance for emitting annotated
            logs related to the request.

        :returns: A :py:class:`StateMachine` object.

        """
        raise NotImplementedError()

    def getDeleteStateMachine(self, external_id, log):
        """Return a state machine suitable for deleting an instance

        This method should return a new state machine object
        initialized to delete the described instance.

        :param str or dict external_id: The external_id of the instance, as
            supplied by a creation StateMachine or an Instance.
        :param log Logger: A logger instance for emitting annotated
            logs related to the request.
        """
        raise NotImplementedError()

    def listInstances(self):
        """Return an iterator of instances accessible to this provider.

        The yielded values should represent all instances accessible
        to this provider, not only those under the control of this
        adapter, but all visible instances in order to achive accurate
        quota calculation.

        :returns: A generator of :py:class:`Instance` objects.
        """
        raise NotImplementedError()

    def listResources(self):
        """Return a list of resources accessible to this provider.

        The yielded values should represent all resources accessible
        to this provider, not only those under the control of this
        adapter, but all visible instances in order for the driver to
        identify leaked resources and instruct the adapter to remove
        them.

        :returns: A generator of :py:class:`Resource` objects.
        """
        raise NotImplementedError()

    def deleteResource(self, resource):
        """Delete the supplied resource

        The driver has identified a leaked resource and the adapter
        should delete it.

        :param Resource resource: A Resource object previously
            returned by 'listResources'.
        """
        raise NotImplementedError()

    def getQuotaLimits(self):
        """Return the quota limits for this provider

        The default implementation returns a simple QuotaInformation
        with no limits.  Override this to provide accurate
        information.

        :returns: A :py:class:`QuotaInformation` object.

        """
        return QuotaInformation(default=math.inf)

    def getQuotaForLabel(self, label):
        """Return information about the quota used for a label

        The default implementation returns a simple QuotaInformation
        for one instance; override this to return more detailed
        information including cores and RAM.

        :param ProviderLabel label: A config object describing
            a label for an instance.

        :returns: A :py:class:`QuotaInformation` object.
        """
        return QuotaInformation(instances=1)

    def getAZs(self):
        """Return a list of availability zones for this provider

        One of these will be selected at random and supplied to the
        create state machine.  If a request handler is building a node
        set from an existing ready node, then the AZ from that node
        will be used instead of the results of this method.

        :returns: A list of availability zone names.
        """
        return [None]

    def labelReady(self, label):
        """Indicate whether a label is ready in the provided cloud

        This is used by the launcher to determine whether it should
        consider a label to be in-service for a provider.  If this
        returns False, the label will be ignored for this provider.

        This does not need to consider whether a diskimage is ready;
        the launcher handles that itself.  Instead, this can be used
        to determine whether a cloud-image is available.

        :param ProviderLabel label: A config object describing a label
            for an instance.

        :returns: A bool indicating whether the label is ready.
        """
        return True

    # The following methods must be implemented only if image
    # management is supported:

    def uploadImage(self, provider_image, image_name, filename,
                    image_format=None, metadata=None, md5=None,
                    sha256=None):
        """Upload the image to the cloud

        :param provider_image ProviderImageConfig:
            The provider's config for this image
        :param image_name str: The name of the image
        :param filename str: The path to the local file to be uploaded
        :param image_format str: The format of the image (e.g., "qcow")
        :param metadata dict: A dictionary of metadata that must be
            stored on the image in the cloud.
        :param md5 str: The md5 hash of the image file
        :param sha256 str: The sha256 hash of the image file

        :return: The external id of the image in the cloud
        """
        raise NotImplementedError()

    def deleteImage(self, external_id):
        """Delete an image from the cloud

        :param external_id str: The external id of the image to delete
        """
        raise NotImplementedError()

    # The following methods are optional
    def getConsoleLog(self, label, external_id):
        """Return the console log from the specified server

        :param label ConfigLabel: The label config for the node
        :param external_id str or dict: The external id of the server
        """
        raise NotImplementedError()

    def notifyNodescanFailure(self, label, external_id):
        """Notify the adapter of a nodescan failure

        :param label ConfigLabel: The label config for the node
        :param external_id str or dict: The external id of the server
        """
        pass
