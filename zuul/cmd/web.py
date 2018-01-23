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

from zuul.driver.sql import sqlconnection
from zuul.driver.github import githubconnection
from zuul.lib.config import get_default


class WebServer(zuul.cmd.ZuulDaemonApp):
    app_name = 'web'
    app_description = 'A standalone Zuul web server.'

    def exit_handler(self, signum, frame):
        self.web.stop()

    def _run(self):
        info = zuul.model.WebInfo()
        info.websocket_url = get_default(self.config,
                                         'web', 'websocket_url', None)
        info.graphite_url = get_default(self.config,
                                        'web', 'graphite_url', None)
        # We call this graphite_prefix in the info record because it's used
        # to interact with graphite.
        info.graphite_prefix = get_default(self.config, 'statsd', 'prefix')

        params = dict()

        params['info'] = info
        params['listen_address'] = get_default(self.config,
                                               'web', 'listen_address',
                                               '127.0.0.1')
        params['listen_port'] = get_default(self.config, 'web', 'port', 9000)
        params['static_cache_expiry'] = get_default(self.config, 'web',
                                                    'static_cache_expiry',
                                                    3600)
        params['gear_server'] = get_default(self.config, 'gearman', 'server')
        params['gear_port'] = get_default(self.config, 'gearman', 'port', 4730)
        params['ssl_key'] = get_default(self.config, 'gearman', 'ssl_key')
        params['ssl_cert'] = get_default(self.config, 'gearman', 'ssl_cert')
        params['ssl_ca'] = get_default(self.config, 'gearman', 'ssl_ca')

        # TODO(mordred) Update plugin interface to allow plugins to be
        # able to register endpoints and to indicate that they provide
        # capabilities.
        sql_conn_name = get_default(self.config, 'web',
                                    'sql_connection_name')
        sql_conn = None
        if sql_conn_name:
            # we want a specific sql connection
            sql_conn = self.connections.connections.get(sql_conn_name)
            if not sql_conn:
                self.log.error("Couldn't find sql connection '%s'" %
                               sql_conn_name)
                sys.exit(1)
        else:
            # look for any sql connection
            connections = [c for c in self.connections.connections.values()
                           if isinstance(c, sqlconnection.SQLConnection)]
            if len(connections) > 1:
                self.log.error("Multiple sql connection found, "
                               "set the sql_connection_name option "
                               "in zuul.conf [web] section")
                sys.exit(1)
            if connections:
                # use this sql connection by default
                sql_conn = connections[0]
        params['sql_connection'] = sql_conn
        if sql_conn:
            info.capabilities.job_history = True

        params['github_connections'] = {}
        for conn_name, connection in self.connections.connections.items():
            if isinstance(connection, githubconnection.GithubConnection):
                try:
                    token = connection.connection_config['webhook_token']
                except KeyError as e:
                    self.log.exception("Error reading webhook token:")
                    sys.exit(1)
                params['github_connections'][conn_name] = token

        try:
            self.web = zuul.web.ZuulWeb(**params)
        except Exception as e:
            self.log.exception("Error creating ZuulWeb:")
            sys.exit(1)

        loop = asyncio.get_event_loop()
        signal.signal(signal.SIGUSR1, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

        self.log.info('Zuul Web Server starting')
        self.thread = threading.Thread(target=self.web.run,
                                       args=(loop,),
                                       name='web')
        self.thread.start()

        self.thread.join()
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
