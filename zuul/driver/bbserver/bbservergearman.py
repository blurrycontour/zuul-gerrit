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
import json

from zuul.lib.gearworker import ZuulGearWorker
from zuul.lib.logutil import get_annotated_logger


class BitbucketServerGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.BitbucketServerGearmanWorker")

    def __init__(self, connection):
        self.config = connection.sched.config
        self.connection = connection

        handler = f"bitbucketserver:{self.connection.connection_name}:payload"
        self.jobs = {
            handler: self.handle_payload,
        }
        self.gearworker = ZuulGearWorker(
            'Zuul Bitbucket Server Worker',
            'zuul.BitbucketServerGearmanWorker',
            'bitbucketserver-gearman-worker',
            self.config,
            self.jobs)

    def handle_payload(self, job):
        args = json.loads(job.arguments)
        headers = args["headers"]
        body = args["body"]

        request_id = headers.get("x-request-id", "undefined")
        event = headers["x-event-key"]

        log = get_annotated_logger(self.log, request_id)
        log.info(f"Bitbucket Webhook Received event: {event}")

        try:
            self.__dispatch_event(body, event, request_id, log)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling Bitbucket Server event:")

        job.sendWorkComplete(json.dumps(output))

    def __dispatch_event(self, body, event, request_id, log):
        log.debug(body)
        try:
            log.info(f"Dispatching event {event}")
            self.connection.addEvent(body, event, request_id)
        except Exception as err:
            message = f'Exception dispatching event: {err}'
            log.exception(message)
            raise Exception(message)

    def start(self):
        self.gearworker.start()

    def stop(self):
        self.gearworker.stop()
