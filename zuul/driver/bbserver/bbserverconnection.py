# Copyright 2020 Motional.
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

import logging
import threading
import json
import queue
from urllib.parse import urlparse

import cherrypy
import voluptuous as v
import time

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController

from zuul.driver.bbserver.bbservergearman import BitbucketServerGearmanWorker


class BitbucketServerEventConnector(threading.Thread):
    """Move events from Bitbucket Server into the scheduler"""

    log = logging.getLogger("zuul.BitbucketServerEventConnector")

    def __init__(self, connection):
        super().__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False

        self.event_handler_mapping = {
            'diagnostics:ping': self._event_ping,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    @staticmethod
    def _event_ping(_):
        # Ping is the dummy event that can be triggered from Bitbucket UI.
        return None

    def _handleEvent(self):
        ts, json_body, event_type, request_id = self.connection.getEvent()
        if self._stopped:
            return

        self.log.info(f"Received event: {event_type}")

        if event_type not in self.event_handler_mapping:
            self.log.error(f"Unhandled BitbucketServer event: {event_type}")
            return

        self.log.debug(f"Handling event: {event_type}")
        try:
            event = self.event_handler_mapping[event_type](json_body)
        except Exception:
            self.log.exception(f"Exception when handling event: {event_type}")
            event = None

        if event:
            event.zuul_event_id = request_id
            event.timestamp = ts
            self.connection.logEvent(event)
            self.connection.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving BitbucketServer event")
            finally:
                self.connection.eventDone()


class BitbucketServerConnection(BaseConnection):
    driver_name = 'bitbucketserver'
    log = logging.getLogger("zuul.BitbucketServerConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super().__init__(driver, connection_name, connection_config)

        self.projects = {}
        self.project_branch_cache = {}
        self._change_cache = {}

        if 'baseurl' not in self.connection_config:
            raise Exception('baseurl is required for Bitbucket '
                            f'connections in {self.connection_name}')
        self.baseurl = self.connection_config.get(
            'baseurl', 'https://bitbucket:7990')

        self.user = self.connection_config.get('user', '')
        self.password = self.connection_config.get('password', '')

        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', urlparse(self.baseurl).netloc)

        self.sched = None
        self.event_queue = queue.Queue()
        self.source = driver.getSource(self)
        self.gearman_worker = None

    def _start_event_connector(self):
        self.bitbucketserver_event_connector = \
            BitbucketServerEventConnector(self)
        self.bitbucketserver_event_connector.start()

    def _stop_event_connector(self):
        if self.bitbucketserver_event_connector:
            self.bitbucketserver_event_connector.stop()
            self.bitbucketserver_event_connector.join()

    def onLoad(self):
        self.log.info(
            f"Starting BitbucketServer connection: {self.connection_name}")
        self.gearman_worker = BitbucketServerGearmanWorker(self)
        self.log.info('Starting event connector')
        self._start_event_connector()
        self.log.info('Starting GearmanWorker')
        self.gearman_worker.start()

    def onStop(self):
        if hasattr(self, 'gearman_worker'):
            self.gearman_worker.stop()
            self._stop_event_connector()

    def addEvent(self, data, event=None, request_id=None):
        return self.event_queue.put((time.time(), data, event, request_id))

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()


class BitbucketServerWebController(BaseWebController):
    log = logging.getLogger("zuul.BitbucketServerWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        headers = cherrypy.request.headers.items()
        headers = {key.lower(): value for key, value in headers}

        json_body = cherrypy.request.body.read()
        self.log.debug("Event header: %s", headers)
        self.log.debug("Event body: %s", json_body)
        body = json.loads(json_body.decode('utf-8'))

        job = self.zuul_web.rpc.submitJob(
            f'bitbucketserver:{self.connection.connection_name}:payload',
            {'headers': headers, 'payload': body}
        )
        return json.loads(job.data[0])


def getSchema():
    return v.Any(str, v.Schema(dict))
