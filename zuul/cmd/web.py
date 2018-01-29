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
from copy import deepcopy
import logging
import signal
import sys
import threading

import zuul.cmd
import zuul.model
import zuul.web

from zuul.lib.config import get_default


class WebServer(zuul.cmd.ZuulDaemonApp):
    app_name = 'web'
    app_description = 'A standalone Zuul web server.'

    def exit_handler(self, signum, frame):
        self.web.stop()

    def _run(self):
        info = zuul.model.WebInfo.fromConfig(self.config)

        params = dict()
        admin_params = dict()

        params['info'] = info
        params['listen_address'] = get_default(self.config,
                                               'web', 'listen_address',
                                               '0.0.0.0')
        params['listen_port'] = get_default(self.config, 'web', 'port', 9000)
        params['static_cache_expiry'] = get_default(self.config, 'web',
                                                    'static_cache_expiry',
                                                    3600)
        params['gear_server'] = get_default(self.config, 'gearman', 'server')
        params['gear_port'] = get_default(self.config, 'gearman', 'port', 4730)
        params['ssl_key'] = get_default(self.config, 'gearman', 'ssl_key')
        params['ssl_cert'] = get_default(self.config, 'gearman', 'ssl_cert')
        params['ssl_ca'] = get_default(self.config, 'gearman', 'ssl_ca')

        params['connections'] = []
        admin_params = deepcopy(params)
        # Validate config here before we spin up the ZuulWeb object
        for conn_name, connection in self.connections.connections.items():
            try:
                if connection.validateWebConfig(self.config, self.connections):
                    params['connections'].append(connection)
                    # this cannot be deepcopied
                    admin_params['connections'].append(connection)
            except Exception:
                self.log.exception("Error validating config")
                sys.exit(1)

        try:
            self.web = zuul.web.ZuulWeb(**params)
        except Exception as e:
            self.log.exception("Error creating ZuulWeb:")
            sys.exit(1)

        if (get_default(self.config, 'web',
                        'admin_listen_address', None) and
            get_default(self.config, 'web',
                        'admin_port', None)):
            admin_addr = get_default(self.config, 'web',
                                     'admin_listen_address', None)
            admin_port = get_default(self.config, 'web', 'admin_port', None)
            admin_params['listen_address'] = admin_addr
            admin_params['listen_port'] = admin_port
        elif (get_default(self.config, 'web',
                          'admin_listen_address', None) or
              get_default(self.config, 'web',
                          'admin_port', None)):
            self.log.exception(
                'Incomplete parameters: define '
                'admin_listen_address and admin_port')
            sys.exit(1)
        else:
            admin_params = dict()

        loop = asyncio.get_event_loop()
        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('Zuul Web Server starting')
        self.thread = threading.Thread(target=self.web.run,
                                       args=(loop,),
                                       name='web')
        self.thread.start()

        if admin_params:
            try:
                self.admin_web = zuul.web.ZuulAdminWeb(**admin_params)
                self.log.info('Zuul Web Admin Server starting')
                self.admin_thread = threading.Thread(target=self.admin_web.run,
                                                     args=(loop,),
                                                     name='webAdmin')
                self.admin_thread.start()

            except Exception as e:
                self.log.exception("Error creating ZuulAdminWeb:")
                sys.exit(1)

        try:
            signal.pause()
        except KeyboardInterrupt:
            print("Ctrl + C: asking web server to exit nicely...\n")
            self.exit_handler(signal.SIGINT, None)

        self.thread.join()
        if admin_params:
            self.admin_thread.join()
        loop.stop()
        loop.close()
        self.log.info("Zuul Web Server stopped")

    def run(self):
        self.setup_logging('web', 'log_config')
        self.log = logging.getLogger("zuul.WebServer")

        self.configure_connections()

        try:
            self._run()
        except Exception:
            self.log.exception("Exception from WebServer:")


def main():
    WebServer().main()


if __name__ == "__main__":
    main()
