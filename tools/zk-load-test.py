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

import argparse
import itertools
import logging
from multiprocessing import Process
import random
import socket
import ssl
import time
import uuid

import kazoo.client
from kazoo.exceptions import NoNodeError

# This runs a ZK load test roughly based on how Zuul uses ZK.  It can
# be used to evaluate how ZK server configurations as well as changes
# to Zuul might affect overall performance.

# The best measures of performance appear to be the zk_avg_latency in
# combination with the achieved throughput of the operations in this
# script.

# A global setting to slow down writes.  The cache and pipeline
# simulators completely rewrite the data continuously which isn't
# exactly how we use the system.  This slows writes down so that ZK
# doesn't spend quite as much time writing to disk.
WRITE_DELAY = 0.001

# If running ZK locally on a tmpfs, it may help to run this command to
# continuously delete snapshots and journals:
# while true; do
#   docker exec -it zk01 bash -c \
#     'rm /datalog/version-2/log.* /data/version-2/snapshot.*';
#   docker exec -it zk02 bash -c \
#     'rm /datalog/version-2/log.* /data/version-2/snapshot.*';
#   docker exec -it zk03 bash -c \
#     'rm /datalog/version-2/log.* /data/version-2/snapshot.*';
#   sleep 10;
# done

logging.basicConfig(level=logging.INFO)
l = logging.getLogger('kazoo')
l.setLevel(logging.INFO)
l.propagate = False


def generate_data(size):
    "Generates random data to store in znodes"
    return random.randbytes(size)


def get_client(conn_info):
    kwargs = {}
    if conn_info.cert:
        kwargs['use_ssl'] = True
        kwargs['keyfile'] = conn_info.key
        kwargs['certfile'] = conn_info.cert
        kwargs['ca'] = conn_info.ca
    client = kazoo.client.KazooClient(conn_info.connection_str, **kwargs)
    client.start()
    return client


class ConnectionInfo:
    def __init__(self, connection_str, cert, key, ca):
        self.cert = cert
        self.key = key
        self.ca = ca
        self.connection_str = connection_str


class Socket:
    "Used by the ZooKeeperStats class"
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
    "Output ZK stats periodically."

    # Comment out the ones that aren't interesting to reduce the
    # output.
    GAUGES = [
        'zk_avg_latency',
        'zk_min_latency',
        'zk_max_latency',
        'zk_outstanding_requests',
        'zk_znode_count',
        # 'zk_followers',
        # 'zk_synced_followers',
        # 'zk_pending_syncs',
        'zk_watch_count',
        'zk_ephemerals_count',
        'zk_approximate_data_size',
        # 'zk_open_file_descriptor_count',
        # 'zk_max_file_descriptor_count',
    ]

    COUNTERS = [
        # 'zk_packets_received',
        # 'zk_packets_sent',
    ]

    def __init__(self, conn_info, namespace):
        self.COUNTERS.append('zk_read_per_namespace_count{key="%s"}'
                             % namespace)
        self.COUNTERS.append('zk_write_per_namespace_count{key="%s"}'
                             % namespace)
        self.namespace = namespace
        conn_str = conn_info.connection_str.split(',')[0]
        host, port = conn_str.split(':')
        port = int(port)
        self.socket = Socket(host, port,
                             conn_info.ca, conn_info.cert, conn_info.key)
        self.log = logging.getLogger("ZooKeeperStats")
        # Contains raw gauge and count data
        self.prevdata = {}
        # Contains count deltas
        self.interval_count = {}
        self.rate_frames = []
        self.last_stats = time.monotonic()

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
        for key in self.GAUGES:
            try:
                value = stats.get(key, '0')
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
                self.log.info('%s %s', key, value)
            except Exception:
                self.log.exception("Unable to process %s", key)
        for key in self.COUNTERS:
            try:
                newvalue = int(float(stats.get(key, 0)))
                oldvalue = self.prevdata.get(key)
                if oldvalue is not None:
                    value = newvalue - oldvalue
                    self.log.info('%s %s', key, value)
                    self.interval_count[key] = value
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
        time.sleep(10)
        stats = self.getStats()
        self.reportStats(stats)
        now = time.monotonic()
        delta = now - self.last_stats
        self.last_stats = now

        if self.interval_count:
            read_ops = self.interval_count[
                'zk_read_per_namespace_count{key="%s"}' % self.namespace]
            write_ops = self.interval_count[
                'zk_write_per_namespace_count{key="%s"}' % self.namespace]

            # Smooth over a 1 minute average
            while len(self.rate_frames) > 6:
                self.rate_frames.pop(0)
            self.rate_frames.append((read_ops, write_ops, delta))

            total_read_ops = sum([x[0] for x in self.rate_frames])
            total_write_ops = sum([x[1] for x in self.rate_frames])
            total_delta = sum([x[2] for x in self.rate_frames])
            read_rate = round(total_read_ops / total_delta)
            write_rate = round(total_write_ops / total_delta)
            self.log.info(
                f'Read ops/sec {read_rate}, write ops/sec {write_rate}')


class QueueSimulator:
    "Simulate a queue in ZK"

    # The size in bytes of each object in the queue.
    OBJECT_SIZE = 100

    def __init__(self, conn_info, namespace, name, size):
        self.conn_info = conn_info
        self.name = name
        self.path = f'/{namespace}/queue/{name}'
        self.queue_size = size

    def init(self):
        self.log = logging.getLogger('QueueSimulator')
        self.chunk_ops = 0
        self.chunk_start = time.monotonic()
        self.running = True
        self.client = get_client(self.conn_info)
        self.client.ensure_path(self.path)
        self.client.ensure_path(f'{self.path}/items')
        self.client.ensure_path(f'{self.path}/locks')

    def check_timing(self, thread):
        now = time.monotonic()
        delta = now - self.chunk_start
        if delta >= 10:
            rate = self.chunk_ops / delta
            self.log.debug(f'Queue {self.name} {thread} ops/sec {rate}')
            self.chunk_start = now
            self.chunk_ops = 0

    def get_current_queue(self):
        self.chunk_ops += 1
        return self.client.get_children(f'{self.path}/items')

    def get_current_queue_size(self):
        return len(self.get_current_queue())

    def add_item(self):
        uid = uuid.uuid4().hex
        path = f'{self.path}/items/{uid}'
        self.log.debug(f'Create {path}')
        self.client.create(path, generate_data(self.OBJECT_SIZE))
        self.chunk_ops += 1

    def delete_item(self, uid):
        path = f'{self.path}/items/{uid}'
        self.log.debug(f'Delete {path}')
        self.client.delete(path)
        self.chunk_ops += 1

    def lock(self, uid):
        path = f'{self.path}/locks/{uid}'
        self.log.debug(f'Lock {path}')
        lock = self.client.Lock(path)
        have_lock = lock.acquire(blocking=False)
        self.chunk_ops += 1
        if have_lock:
            return lock
        else:
            return None

    def unlock(self, lock):
        self.log.debug(f'Unlock {lock.path}')
        lock.release()
        self.chunk_ops += 1

    def producer(self):
        "A processor that produces items in the queue"
        self.init()
        while self.running:
            self.check_timing('producer')
            current = self.get_current_queue_size()
            for x in range(self.queue_size - current):
                self.add_item()
                time.sleep(WRITE_DELAY)

    def consumer(self):
        "A processor that consumes items in the queue"
        self.init()
        while self.running:
            self.check_timing('consumer')
            items = self.get_current_queue()
            for item in items:
                lock = self.lock(item)
                if lock:
                    try:
                        self.delete_item(item)
                    finally:
                        self.unlock(lock)

    def establish_watches(self):
        self._watch_children(None)

    def _watch_children(self, event):
        children = set(self.client.get_children(f'{self.path}/items',
                                                watch=self._watch_children))
        self.chunk_ops += 1
        new_children = children - self.last_children
        for child in new_children:
            self._watch_child(None, path=f'{self.path}/items/{child}')
            self.chunk_ops += 1
        self.last_children = children

    def _watch_child(self, event, path=None):
        path = path or event.path
        self.log.debug(f'Fetch {path}')
        try:
            self.client.get(path, watch=self._watch_child)
            self.chunk_ops += 1
        except NoNodeError:
            pass

    def watcher(self):
        "A processor that watches the queue"
        self.init()
        self.last_children = set()
        self.establish_watches()
        while self.running:
            self.check_timing('watcher')
            time.sleep(0.1)


class CacheSimulator:
    """Simulate a cache in ZK

    The same objects will be continuously re-written with new data.
    """
    # The size of each item in bytes.
    OBJECT_SIZE = 100

    def __init__(self, conn_info, namespace, name, size):
        self.conn_info = conn_info
        self.name = name
        self.path = f'/{namespace}/cache/{name}'
        self.cache_size = size

    def init(self):
        self.log = logging.getLogger('CacheSimulator')
        self.chunk_ops = 0
        self.chunk_start = time.monotonic()
        self.running = True
        self.client = get_client(self.conn_info)
        self.client.ensure_path(self.path)
        self.client.ensure_path(f'{self.path}/items')
        self.client.ensure_path(f'{self.path}/locks')

    def check_timing(self, thread, count=None):
        now = time.monotonic()
        delta = now - self.chunk_start
        if delta >= 10:
            rate = self.chunk_ops / delta
            if count is None:
                count = ''
            else:
                count = f' count {count}'
            self.log.debug(f'Cache {self.name} {thread} ops/sec {rate}{count}')
            self.chunk_start = now
            self.chunk_ops = 0

    def write_item(self, uid):
        path = f'{self.path}/items/{uid}'
        self.log.debug(f'Create {path}')
        if self.client.exists(path):
            self.client.set(path, generate_data(self.OBJECT_SIZE))
        else:
            self.client.create(path, generate_data(self.OBJECT_SIZE))
        self.chunk_ops += 2

    def creator(self):
        "A processor that creates items in the cache"
        self.init()
        while self.running:
            for x in range(self.cache_size):
                if x % 1000 == 0:
                    self.check_timing('creator', x)
                self.write_item(x)
                time.sleep(WRITE_DELAY)

    def establish_watches(self):
        self._watch_children(None)

    def _watch_children(self, event):
        children = set(self.client.get_children(f'{self.path}/items',
                                                watch=self._watch_children))
        self.chunk_ops += 1
        new_children = children - self.last_children
        for child in new_children:
            self._watch_child(None, path=f'{self.path}/items/{child}')
            self.chunk_ops += 1
        self.last_children = children

    def _watch_child(self, event, path=None):
        path = path or event.path
        self.log.debug(f'Fetch {path}')
        try:
            self.client.get(path, watch=self._watch_child)
            self.chunk_ops += 1
        except NoNodeError:
            pass

    def watcher(self):
        "A processor that watches items in the cache"
        self.init()
        self.last_children = set()
        self.establish_watches()
        while self.running:
            self.check_timing('watcher')
            time.sleep(0.1)


class PipelineSimulator:
    "Simulate a pipeline"

    # Number of object path levels:
    PIPELINE_DEPTH = 9
    # Number of objects per level:
    PIPELINE_WIDTH = 3
    # Total objects: $$ \Sigma_{i=1}^{depth} width^i $$
    # Total objects: sum([width**i for i in range(1, depth+1)])

    # When we write object data, we chose a length randomly from this
    # set with the following weights (so most objects are 0 length,
    # and a very few are approximately max size).
    OBJECT_SIZES = [0, 100, (1024 * 1023)]
    OBJECT_WEIGHTS = [0.75, 0.24, 0.01]

    def __init__(self, conn_info, namespace, name):
        self.conn_info = conn_info
        self.name = name
        self.path = f'/{namespace}/pipeline/{name}'

    def init(self):
        self.log = logging.getLogger('PipelineSimulator')
        self.chunk_start = time.monotonic()
        self.read_ops = 0
        self.write_ops = 0
        self.running = True
        self.client = get_client(self.conn_info)
        self.client.ensure_path(self.path)

    def check_timing(self):
        now = time.monotonic()
        delta = now - self.chunk_start
        if delta >= 10:
            read_rate = self.read_ops / delta
            write_rate = self.write_ops / delta
            self.log.debug(f'Pipeline {self.name} read ops/sec {read_rate}')
            self.log.debug(f'Pipeline {self.name} write ops/sec {write_rate}')
            self.chunk_start = now
            self.read_ops = 0
            self.write_ops = 0

    def read_pipeline(self):
        self.read_pipeline_level(self.path)

    def read_pipeline_level(self, path):
        self.check_timing()
        self.read_ops += 1
        for child in self.client.get_children(path):
            obj_path = f'{path}/{child}'
            data, stat = self.client.get(obj_path)
            size = len(data)
            self.log.debug(f'Read {obj_path} size {size}')
            self.read_ops += 1
            self.read_pipeline_level(obj_path)

    def write_pipeline(self):
        self.write_pipeline_level(0)

    def write_pipeline_level(self, level, path=None):
        self.check_timing()
        if level >= self.PIPELINE_DEPTH:
            return
        if path is None:
            path = self.path
        for obj in range(self.PIPELINE_WIDTH):
            self.write_object(path, obj)
            self.write_pipeline_level(level + 1, f'{path}/{obj}')

    def write_object(self, path, obj):
        path = f'{path}/{obj}'
        size = random.choices(self.OBJECT_SIZES, self.OBJECT_WEIGHTS)[0]
        self.log.debug(f'Write {path} size {size}')
        if self.client.exists(path):
            self.client.set(path, generate_data(size))
        else:
            self.client.create(path, generate_data(size))
        self.write_ops += 2
        time.sleep(WRITE_DELAY)

    def processor(self):
        "A processor that reads and writes the pipeline"
        self.init()
        while self.running:
            self.read_pipeline()
            self.write_pipeline()


# The processes that we should (would) join if we actually had an exit
# routine other than CTRL-C:
processes = []


def start_stats(conn_info, namespace):
    "Start the ZK monitoring routine"
    stats = ZooKeeperStats(conn_info, namespace)
    p = Process(target=stats.run)
    p.start()
    processes.append(p)


def start_queues(conn_info, namespace, count, size, read_ratio):
    "Start the specified number of queue simulators"
    for qno in range(count):
        queue = QueueSimulator(conn_info, namespace, qno, size)
        p = Process(target=queue.producer)
        p.start()
        processes.append(p)
        p = Process(target=queue.consumer)
        p.start()
        processes.append(p)
        for x in range(read_ratio):
            p = Process(target=queue.watcher)
            p.start()
            processes.append(p)


def start_caches(conn_info, namespace, count, size, read_ratio):
    "Start the specified number of cache simulators"
    for cno in range(count):
        cache = CacheSimulator(conn_info, namespace, cno, size)
        p = Process(target=cache.creator)
        p.start()
        processes.append(p)
        for x in range(read_ratio):
            p = Process(target=cache.watcher)
            p.start()
            processes.append(p)


def start_pipelines(conn_info, namespace, count):
    "Start the specified number of pipeline simulators"
    for pno in range(count):
        pipeline = PipelineSimulator(conn_info, namespace, pno)
        p = Process(target=pipeline.processor)
        p.start()
        processes.append(p)


def get_subtree(client, path):
    for child in client.get_children(path):
        for item in get_subtree(client, f'{path}/{child}'):
            yield item
    yield path


def batched(iterable, n):
    "Batch data into tuples of length n. The last batch may be shorter."
    # From https://docs.python.org/3/library/itertools.html#itertools-recipes
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while batch := tuple(itertools.islice(it, n)):
        yield batch


def reset(conn_info, namespace):
    "Delete everything from a previous run"
    # This is quite slow; it's better if you can just restart ZK
    # containers.
    client = get_client(conn_info)
    print("Deleting")
    results = []
    root = f'/{namespace}'
    if client.exists(root):
        for chunk in batched(get_subtree(client, root), 1000):
            print('Delete', len(chunk))
            t = client.transaction()
            for path in chunk:
                t.delete(path)
            results.append(t.commit_async())
    print('Await deletion')
    for res in results:
        res.get()
    print("Starting")


def main(conn_info, namespace, read_ratio, queues, caches, pipelines,
         queue_size, cache_size):
    reset(conn_info, namespace)
    start_stats(conn_info, namespace)
    start_queues(conn_info, namespace, queues, queue_size, read_ratio)
    start_caches(conn_info, namespace, caches, cache_size, read_ratio)
    start_pipelines(conn_info, namespace, pipelines)

    for p in processes:
        p.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('host', help='ZK host string')
    parser.add_argument('--cert', help='Path to TLS certificate')
    parser.add_argument('--key', help='Path to TLS key')
    parser.add_argument('--ca', help='Path to TLS CA cert')
    parser.add_argument('--namespace', help='Namespace string',
                        default='load-test')
    parser.add_argument('--read-ratio',
                        type=int,
                        help='''\
The number of additional read-only processors to start for each
queue and cache processor; increasing this increases the
read/write operation ratio that the ZK servers see''',
                        default=16)
    parser.add_argument('--queues',
                        type=int,
                        help='The number of queue processors to start',
                        default=4)
    parser.add_argument('--queue-size',
                        type=int,
                        help='''\
The number of items in each queue; the producer will not let the
queue grow beyond this length in order to avoid runaway resource
consumption''',
                        default=100)
    parser.add_argument('--caches',
                        type=int,
                        help='The number of cache processors to start',
                        default=4)
    parser.add_argument('--cache-size',
                        type=int,
                        help='''\
The number of items in each cache; the producer will not let the
cache grow beyond this length in order to avoid runaway resource
consumption''',
                        default=30000)
    parser.add_argument('--pipelines',
                        type=int,
                        help='The number of pipeline processors to start',
                        default=4)
    args = parser.parse_args()
    conn_info = ConnectionInfo(args.host, args.cert, args.key, args.ca)
    main(conn_info, args.namespace, args.read_ratio, args.queues,
         args.caches, args.pipelines, args.queue_size, args.cache_size)
