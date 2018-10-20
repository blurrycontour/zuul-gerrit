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

import logging
import signal
import sys

import zuul.cmd
import zuul.model
import zuul.web
import zuul.driver.sql
import zuul.driver.github

from zuul.lib.config import get_default


class WebServer(zuul.cmd.ZuulDaemonApp):
    app_name = 'web'
    app_description = 'A standalone Zuul web server.'

    # FIXME(iremizov): move to separate module with defaults
    DEFAULT_WEB_LISTEN_ADDRESS = '127.0.0.1'
    DEFAULT_WEB_PORT = 9000
    DEFAULT_WEB_STATIC_CACHE_EXPIRY = 3600
    DEFAULT_WEB_STATIC_PATH = None
    DEFAULT_GEARMAN_SERVER = None
    DEFAULT_GEARMAN_PORT = 4730
    DEFAULT_GEARMAN_SSL_KEY = None
    DEFAULT_GEARMAN_SSL_CERT = None
    DEFAULT_GEARMAN_SSL_CA = None

    @property
    def log(self):
        return logging.getLogger("zuul.WebServer")

    def exit_handler(self, signum, frame):
        self.log.debug("Signal received: %s %s" % (signum, frame))
        self.web.stop()

    def _run(self):
        info = zuul.model.WebInfo.fromConfig(self.config)

        # Validate config here before we spin up the ZuulWeb object
        for conn_name, connection in self.connections.connections.items():
            try:
                connection.validateWebConfig(self.config, self.connections)
            except Exception:
                self.log.exception("Error validating config")
                sys.exit(1)

        try:
            self.web = zuul.web.ZuulWeb(
                info=info,
                listen_address=get_default(
                    self.config, 'web', 'listen_address',
                    self.DEFAULT_WEB_LISTEN_ADDRESS),
                listen_port=get_default(
                    self.config, 'web', 'port',
                    self.DEFAULT_WEB_PORT),
                static_cache_expiry=get_default(
                    self.config, 'web', 'static_cache_expiry',
                    self.DEFAULT_WEB_STATIC_CACHE_EXPIRY),
                static_path=get_default(
                    self.config, 'web', 'static_path',
                    self.DEFAULT_WEB_STATIC_PATH),
                gear_server=get_default(
                    self.config, 'gearman', 'server',
                    self.DEFAULT_GEARMAN_SERVER),
                gear_port=get_default(
                    self.config, 'gearman', 'port',
                    self.DEFAULT_GEARMAN_PORT),
                ssl_key=get_default(
                    self.config, 'gearman', 'ssl_key',
                    self.DEFAULT_GEARMAN_SSL_KEY),
                ssl_cert=get_default(
                    self.config, 'gearman', 'ssl_cert',
                    self.DEFAULT_GEARMAN_SSL_CERT),
                ssl_ca=get_default(
                    self.config, 'gearman', 'ssl_ca',
                    self.DEFAULT_GEARMAN_SSL_CA),
                connections=self.connections
            )
        except Exception as e:
            self.log.exception("Error creating ZuulWeb:")
            sys.exit(1)

        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('Zuul Web Server starting')
        self.web.start()

        try:
            signal.pause()
        except KeyboardInterrupt:
            print("Ctrl + C: asking web server to exit nicely...\n")
            self.exit_handler(signal.SIGINT, None)

        self.web.stop()
        self.log.info("Zuul Web Server stopped")

    def run(self):
        self.setup_logging('web', 'log_config')

        self.configure_connections(
            include_drivers=[zuul.driver.sql.SQLDriver,
                             zuul.driver.github.GithubDriver])

        try:
            self._run()
        except Exception:
            self.log.exception("Exception from WebServer:")


def main():
    WebServer().main()


if __name__ == "__main__":
    main()
