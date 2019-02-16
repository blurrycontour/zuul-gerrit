# Copyright 2019 Red Hat, Inc.
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

import json
import logging
import queue
import threading

from proton import SSLDomain
from proton.handlers import MessagingHandler
from proton.reactor import Container

from zuul.driver.amqp.amqpmodel import AMQPTriggerEvent
from zuul.connection import BaseConnection
from zuul.exceptions import ConfigurationError


class AMQPEventConnector(threading.Thread):
    """Move events from AMQP to the scheduler."""

    log = logging.getLogger("zuul.AMQPEventConnector")

    def __init__(self, connection):
        super().__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _emitEvent(self, project, tenant, data):
        for branch in project.source.getProjectBranches(project, tenant):
            event = AMQPTriggerEvent()
            event.type = data['type']
            event.address = data['address']
            event.body = data['body']
            event.project_hostname = project.canonical_hostname
            event.project_name = project.name
            event.ref = 'refs/heads/%s' % branch
            event.branch = branch
            self.log.debug("Adding event %s", event)
            self.connection.sched.addEvent(event)

    def _handleEvent(self):
        data = self.connection.getEvent()
        if self._stopped:
            return
        # Inject trigger event for each project configured
        driver = self.connection.driver
        for tenant_name, pipelines in driver.tenants.items():
            tenant = driver.sched.abide.tenants.get(tenant_name)
            for project_name, pcs in tenant.layout.project_configs.items():
                pcst = tenant.layout.getAllProjectConfigs(project_name)
                for pipeline in pipelines:
                    if not [True for pc in pcst if pipeline in pc.pipelines]:
                        continue
                    (trusted, project) = tenant.getProject(project_name)
                    self._emitEvent(project, tenant, data)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving AMQP event:")
            finally:
                self.connection.eventDone()


class AMQPClient(MessagingHandler):
    log = logging.getLogger("zuul.AMQPClient")

    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.conn = None

    def stop(self):
        if self.conn:
            self.conn.close()

    def on_start(self, event):
        self.log.debug("Connecting to %s", self.connection.urls)
        self.container = event.container
        if self.connection.ssl_domain:
            sasl_enabled = True
        else:
            sasl_enabled = False
        self.conn = event.container.connect(
            urls=self.connection.urls,
            ssl_domain=self.connection.ssl_domain,
            sasl_enabled=sasl_enabled)
        self.receiver = event.container.create_receiver(
            self.conn, source=self.connection.address)

    def on_link_error(self, event):
        self.log.warning("Couldn't connect to %s", self.connection.urls)
        event.connection.close()

    def on_transport_error(self, event):
        condition = event.transport.condition
        if condition:
            self.log.warning('Transport error: %s: %s',
                             condition.name, condition.description)
            if condition.name in self.fatal_conditions:
                event.connection.close()
        else:
            self.log.warning("Unspecified transport error")
            self.log.debug('Unspecified transport error')

    def on_message(self, event):
        data = {
            'type': 'message-published',
            'address': event.message.address,
        }
        try:
            data['body'] = json.loads(event.message.body)
        except TypeError:
            data['body'] = event.message.body
        self.log.debug("Received data from AMQP: %s", data)
        self.connection.addEvent(data)


class AMQPWatcher(threading.Thread):
    log = logging.getLogger("zuul.AMQPWatcher")

    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.client = None

    def stop(self):
        self.log.debug("Stopping watcher")
        if self.client:
            self.client.stop()

    def run(self):
        self.client = AMQPClient(self.connection)
        Container(self.client).run()


class AMQPConnection(BaseConnection):
    driver_name = 'amqp'
    log = logging.getLogger("zuul.AMQPConnection")

    def __init__(self, driver, connection_name, connection_config):
        super().__init__(driver, connection_name, connection_config)
        urls = self.connection_config.get('urls')
        if not urls:
            raise ConfigurationError(
                'urls is required for amqp connection in %s' %
                self.connection_name)
        self.urls = urls.split(';')
        self.address = self.connection_config.get('address')
        if not self.address:
            raise ConfigurationError(
                'address is required for amqp connection in %s' %
                self.connection_name)
        if self.connection_config.get('ca_certs'):
            domain = SSLDomain(SSLDomain.MODE_CLIENT)
            certfile = self.connection_config.get('certfile')
            key_file = self.connection_config.get('key_file')
            if not certfile or not key_file:
                raise ConfigurationError(
                    'TLS requires the certfile and key_file options in %s' %
                    self.connection_name)
            domain.set_trusted_ca_db(self.connection_config.get('ca_certs'))
            domain.set_credentials(certfile, key_file, None)
            domain.set_peer_authentication(SSLDomain.VERIFY_PEER)
        else:
            domain = None
        self.ssl_domain = domain
        self.event_queue = queue.Queue()
        self.watcher_thread = None
        self.connector_thread = None

    def onLoad(self):
        self.log.debug("Starting AMQP Connection/Watchers")
        self._start_watcher_thread()
        self._start_event_connector()

    def onStop(self):
        self.log.debug("Stopping AMQP Connection/Watchers")
        self._stop_watcher_thread()
        self._stop_event_connector()

    def _stop_watcher_thread(self):
        if self.watcher_thread:
            self.watcher_thread.stop()
            self.watcher_thread.join()

    def _start_watcher_thread(self):
        self.watcher_thread = AMQPWatcher(self)
        self.watcher_thread.start()

    def _stop_event_connector(self):
        if self.connector_thread:
            self.connector_thread.stop()
            self.connector_thread.join()

    def _start_event_connector(self):
        self.connector_thread = AMQPEventConnector(self)
        self.connector_thread.start()

    def addEvent(self, data):
        return self.event_queue.put(data)

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()
