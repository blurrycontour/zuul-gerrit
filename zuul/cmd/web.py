#!/usr/bin/env python
# Copyright 2017 Red Hat, Inc.
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

import asyncio
import logging
import signal
import sys
import threading

import zuul.cmd
import zuul.model
import zuul.web

from zuul.lib.config import get_default


class WebServer(zuul.cmd.ZuulDaemonApp):
    app_name = 'Zuul Web'
    app_description = 'A standalone Zuul web server.'
    constructor = zuul.web.ZuulWeb

    def exit_handler(self, signum, frame):
        self.web.stop()

    @property
    def params(self):
        return self._params()

    def _params(self):
        params = dict()
        info = zuul.model.WebInfo.fromConfig(self.config)
        params['admin'] = get_default(self.config, 'web',
                                      'enable_admin_endpoint',
                                      False)
        params['info'] = info
        params['listen_address'] = get_default(self.config,
                                               'web', 'listen_address',
                                               '0.0.0.0')
        params['listen_port'] = get_default(self.config, 'web', 'port', 9000)
        params['static_cache_expiry'] = get_default(self.config, 'web',
                                                    'static_cache_expiry',
                                                    3600)
        params['static_path'] = get_default(self.config,
                                            'web', 'static_path',
                                            None)
        params['gear_server'] = get_default(self.config, 'gearman', 'server')
        params['gear_port'] = get_default(self.config, 'gearman', 'port', 4730)
        params['ssl_key'] = get_default(self.config, 'gearman', 'ssl_key')
        params['ssl_cert'] = get_default(self.config, 'gearman', 'ssl_cert')
        params['ssl_ca'] = get_default(self.config, 'gearman', 'ssl_ca')

        params['connections'] = []
        # Validate config here before we spin up the ZuulWeb object
        for conn_name, connection in self.connections.connections.items():
            try:
                if connection.validateWebConfig(self.config, self.connections):
                    params['connections'].append(connection)
            except Exception:
                self.log.exception("Error validating config")
                sys.exit(1)
        return params

    def _run(self):
        try:
            self.web = self.constructor(**self.params)
        except Exception:
            self.log.exception("Error creating %s:" % self.app_name)
            sys.exit(1)

        loop = asyncio.get_event_loop()
        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('%s starting' % self.app_name)
        self.thread = threading.Thread(target=self.web.run,
                                       args=(loop,),
                                       name=self.app_name)
        self.thread.start()

        try:
            signal.pause()
        except KeyboardInterrupt:
            print("Ctrl + C: asking %s to exit nicely...\n" % self.app_name)
            self.exit_handler(signal.SIGINT, None)

        self.thread.join()
        loop.stop()
        loop.close()
        self.log.info("self.app_name stopped")

    def run(self):
        self.setup_logging('web', 'log_config')
        self.log = logging.getLogger("zuul.%s" % self.__class__.__name__)

        self.configure_connections()

        try:
            self._run()
        except Exception:
            self.log.exception("Exception from %s" % self.__class__.__name__)


def main():
    WebServer().main()


if __name__ == "__main__":
    main()
