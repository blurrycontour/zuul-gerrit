#!/usr/bin/env python3

# Copyright (C) 2015 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2021-2022 Acme Gating, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import socket
import time
import os
import ssl

INTERVAL = 10
GAUGES = [
    'zk_avg_latency',
    'zk_min_latency',
    'zk_max_latency',
    'zk_outstanding_requests',
    'zk_znode_count',
    'zk_followers',
    'zk_synced_followers',
    'zk_pending_syncs',
    'zk_watch_count',
    'zk_ephemerals_count',
    'zk_approximate_data_size',
    'zk_open_file_descriptor_count',
    'zk_max_file_descriptor_count',
]

COUNTERS = [
    'zk_packets_received',
    'zk_packets_sent',
]


class Socket:
    def __init__(self, host, port, ca_cert, client_cert, client_key):
        self.host = host
        self.port = port
        self.ca_cert = ca_cert
        self.client_cert = client_cert
        self.client_key = client_key
        self.socket = None

    def open(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        if self.client_key:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(self.ca_cert)
            context.load_cert_chain(self.client_cert, self.client_key)
            context.check_hostname = False
            s = context.wrap_socket(s, server_hostname=self.host)
        s.connect((self.host, self.port))
        self.socket = s

    def __enter__(self):
        self.open()
        return self.socket

    def __exit__(self, etype, value, tb):
        self.socket.close()
        self.socket = None


class ZooKeeperStats:
    def __init__(self, host, port=None,
                 ca_cert=None, client_cert=None, client_key=None):
        if client_key:
            port = port or 2281
        else:
            port = port or 2181
        self.socket = Socket(host, port, ca_cert, client_cert, client_key)
        # The hostname to use when reporting stats (e.g., zk01)
        if host in ('localhost', '127.0.0.1', '::1'):
            self.hostname = socket.gethostname()
        else:
            self.hostname = host
        self.log = logging.getLogger("ZooKeeperStats")
        self.prevdata = {}

    def command(self, command):
        with self.socket as socket:
            socket.send((command + '\n').encode('utf8'))
            data = ''
            while True:
                r = socket.recv(4096)
                data += r.decode('utf8')
                if not r:
                    break
            return data

    def getStats(self):
        data = self.command('mntr')
        lines = data.split('\n')
        ret = []
        for line in lines:
            if not line:
                continue
            if '\t' not in line:
                continue
            key, value = line.split('\t')
            ret.append((key, value))
        return dict(ret)

    def reportStats(self, stats):
        base = 'zk.%s.' % (self.hostname,)
        print()
        for key in GAUGES:
            try:
                value = stats.get(key, '0')
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
                print(base + key, value)
            except Exception:
                self.log.exception("Unable to process %s", key)
        for key in COUNTERS:
            try:
                newvalue = int(stats.get(key, 0))
                oldvalue = self.prevdata.get(key)
                if oldvalue is not None:
                    value = newvalue - oldvalue
                    print(base + key, value)
                self.prevdata[key] = newvalue
            except Exception:
                self.log.exception("Unable to process %s", key)

    def run(self):
        while True:
            try:
                self._run()
            except Exception:
                self.log.exception("Exception in main loop:")

    def _run(self):
        time.sleep(INTERVAL)
        stats = self.getStats()
        self.reportStats(stats)


ca_cert = os.environ.get("ZK_CA_CERT")
client_cert = os.environ.get("ZK_CLIENT_CERT")
client_key = os.environ.get("ZK_CLIENT_KEY")

logging.basicConfig(level=logging.DEBUG)
p = ZooKeeperStats('localhost', ca_cert=ca_cert,
                   client_cert=client_cert, client_key=client_key)
p.run()
