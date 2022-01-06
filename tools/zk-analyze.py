# Copyright 2022 Acme Gating, LLC
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

# Analyze the contents of the ZK tree (whether in ZK or a dump on the
# local filesystem) to identify large objects.

import argparse
import os
import sys
import json
import zlib

import kazoo.client


class SummaryLine:
    def __init__(self, kind, path, size=0):
        self.kind = kind
        self.path = path
        self.size = size
        self.attrs = {}
        self.children = []

    @property
    def tree_size(self):
        return sum([x.tree_size for x in self.children] + [self.size])

    def add(self, child):
        self.children.append(child)

    def __str__(self):
        indent = 0
        return self.toStr(indent)

    def toStr(self, indent, depth=None):
        if depth and indent >= depth:
            return ''
        attrs = ' '.join([f'{k}={v}' for k, v in self.attrs.items()])
        if attrs:
            attrs = ' ' + attrs
        ret = ('  ' * indent + f"{self.kind} {self.path} "
               f"size={self.size} tree={self.tree_size}{attrs}\n")
        for child in self.children:
            ret += child.toStr(indent + 1, depth)
        return ret


class Data:
    def __init__(self, path, raw, failed=False):
        self.path = path
        self.raw = raw
        self.failed = failed
        if not failed:
            self.data = json.loads(raw)
        else:
            print(f"!!! {path} failed to load data")
            self.data = {}

    @property
    def size(self):
        return len(self.raw)


class Tree:
    def getNode(self, path):
        pass

    def listChildren(self, path):
        pass

    def listConnections(self):
        return self.listChildren('/zuul/cache/connection')

    def getBranchCache(self, connection):
        return self.getShardedNode(f'/zuul/cache/connection/{connection}'
                                   '/branches/data')

    def listCacheKeys(self, connection):
        return self.listChildren(f'/zuul/cache/connection/{connection}/cache')

    def getCacheKey(self, connection, key):
        return self.getNode(f'/zuul/cache/connection/{connection}/cache/{key}')

    def listCacheData(self, connection):
        return self.listChildren(f'/zuul/cache/connection/{connection}/data')

    def getCacheData(self, connection, key):
        return self.getShardedNode(f'/zuul/cache/connection/{connection}'
                                   f'/data/{key}')

    def listTenants(self):
        return self.listChildren('/zuul/tenant')

    def listPipelines(self, tenant):
        return self.listChildren(f'/zuul/tenant/{tenant}/pipeline')

    def getPipeline(self, tenant, pipeline):
        return self.getNode(f'/zuul/tenant/{tenant}/pipeline/{pipeline}')

    def getItems(self, tenant, pipeline):
        pdata = self.getPipeline(tenant, pipeline)
        for queue in pdata.data.get('queues', []):
            qdata = self.getNode(queue)
            for item in qdata.data.get('queue', []):
                idata = self.getNode(item)
                yield idata

    def listBuildsets(self, item):
        return self.listChildren(f'{item}/buildset')

    def getBuildset(self, item, buildset):
        return self.getNode(f'{item}/buildset/{buildset}')

    def listJobs(self, buildset):
        return self.listChildren(f'{buildset}/job')

    def getJob(self, buildset, job_name):
        return self.getNode(f'{buildset}/job/{job_name}')

    def listBuilds(self, buildset, job_name):
        return self.listChildren(f'{buildset}/job/{job_name}/build')

    def getBuild(self, buildset, job_name, build):
        return self.getNode(f'{buildset}/job/{job_name}/build/{build}')


class FilesystemTree(Tree):
    def __init__(self, root):
        self.root = root

    def getNode(self, path):
        path = path.lstrip('/')
        fullpath = os.path.join(self.root, path)
        if not os.path.exists(fullpath):
            return Data(path, '', failed=True)
        try:
            with open(os.path.join(fullpath, 'ZKDATA')) as f:
                data = Data(path, f.read())
                return data
        except Exception:
            return Data(path, '', failed=True)

    def getShardedNode(self, path):
        path = path.lstrip('/')
        fullpath = os.path.join(self.root, path)
        if not os.path.exists(fullpath):
            return Data(path, '', failed=True)
        shards = sorted([x for x in os.listdir(fullpath)
                         if x != 'ZKDATA'])
        data = b''
        try:
            for shard in shards:
                with open(os.path.join(fullpath, shard, 'ZKDATA'), 'rb') as f:
                    data += f.read()
            data = zlib.decompress(data)
            return Data(path, data)
        except Exception:
            return Data(path, data, failed=True)

    def listChildren(self, path):
        path = path.lstrip('/')
        fullpath = os.path.join(self.root, path)
        if not os.path.exists(fullpath):
            return []
        return [x for x in os.listdir(fullpath)
                if x != 'ZKDATA']


class ZKTree(Tree):
    def __init__(self, host, cert, key, ca):
        kwargs = {}
        if cert:
            kwargs['use_ssl'] = True
            kwargs['keyfile'] = key
            kwargs['certfile'] = cert
            kwargs['ca'] = ca
        self.client = kazoo.client.KazooClient(host, **kwargs)
        self.client.start()

    def getNode(self, path):
        path = path.lstrip('/')
        if not self.client.exists(path):
            return Data(path, '', failed=True)
        try:
            data, _ = self.client.get(path)
            return data
        except Exception:
            return Data(path, '', failed=True)

    def getShardedNode(self, path):
        path = path.lstrip('/')
        if not self.client.exists(path):
            return Data(path, '', failed=True)
        shards = sorted(self.listChildren(path))
        data = b''
        try:
            for shard in shards:
                d, _ = self.client.get(os.path.join(path, shard))
                data += d
            data = zlib.decompress(data)
            return Data(path, data)
        except Exception:
            return Data(path, data, failed=True)

    def listChildren(self, path):
        path = path.lstrip('/')
        try:
            return self.client.get_children(path)
        except kazoo.client.NoNodeError:
            return []


class Analyzer:
    def __init__(self, args):
        if args.path:
            self.tree = FilesystemTree(args.path)
        else:
            self.tree = ZKTree(args.host, args.cert, args.key, args.ca)
        if args.depth is not None:
            self.depth = int(args.depth)
        else:
            self.depth = None

    def summarizeItem(self, item):
        # Start with an item
        item_summary = SummaryLine('Item', item.path, item.size)
        buildsets = self.tree.listBuildsets(item.path)
        for bs_i, bs_id in enumerate(buildsets):
            # Add each buildset
            buildset = self.tree.getBuildset(item.path, bs_id)
            buildset_summary = SummaryLine('Buildset',
                                           buildset.path, buildset.size)
            item_summary.add(buildset_summary)

            # Some attributes are offloaded, gather them and include
            # the size.
            for x in ['merge_repo_state', 'extra_repo_state', 'files',
                      'config_errors']:
                if buildset.data.get(x):
                    node = self.tree.getShardedNode(buildset.data.get(x))
                    buildset_summary.attrs[x] = node.size
                    buildset_summary.size += node.size

            jobs = self.tree.listJobs(buildset.path)
            for job_i, job_name in enumerate(jobs):
                # Add each job
                job = self.tree.getJob(buildset.path, job_name)
                job_summary = SummaryLine('Job', job.path, job.size)
                buildset_summary.add(job_summary)

                # Handle offloaded job data
                for job_attr in ('artifact_data',
                                 'extra_variables',
                                 'group_variables',
                                 'host_variables',
                                 'secret_parent_data',
                                 'variables',
                                 'parent_data',
                                 'secrets'):
                    job_data = job.data.get(job_attr, None)
                    if job_data and job_data['storage'] == 'offload':
                        node = self.tree.getShardedNode(job_data['path'])
                        job_summary.attrs[job_attr] = node.size
                        job_summary.size += node.size

                builds = self.tree.listBuilds(buildset.path, job_name)
                for build_i, build_id in enumerate(builds):
                    # Add each build
                    build = self.tree.getBuild(
                        buildset.path, job_name, build_id)
                    build_summary = SummaryLine(
                        'Build', build.path, build.size)
                    job_summary.add(build_summary)

                    # Add the offloaded build attributes
                    result_len = 0
                    if build.data.get('_result_data'):
                        result_data = self.tree.getShardedNode(
                            build.data['_result_data'])
                        result_len += len(result_data.raw)
                    if build.data.get('_secret_result_data'):
                        secret_result_data = self.tree.getShardedNode(
                            build.data['_secret_result_data'])
                        result_len += len(secret_result_data.raw)
                    build_summary.attrs['results'] = result_len
                    build_summary.size += result_len
        sys.stdout.write(item_summary.toStr(0, self.depth))

    def summarizePipelines(self):
        for tenant_name in self.tree.listTenants():
            for pipeline_name in self.tree.listPipelines(tenant_name):
                for item in self.tree.getItems(tenant_name, pipeline_name):
                    self.summarizeItem(item)

    def summarizeConnectionCache(self, connection_name):
        connection_summary = SummaryLine('Connection', connection_name, 0)
        branch_cache = self.tree.getBranchCache(connection_name)
        branch_summary = SummaryLine(
            'Branch Cache', connection_name, branch_cache.size)
        connection_summary.add(branch_summary)

        cache_key_summary = SummaryLine(
            'Change Cache Keys', connection_name, 0)
        cache_key_summary.attrs['count'] = 0
        connection_summary.add(cache_key_summary)
        for key in self.tree.listCacheKeys(connection_name):
            cache_key = self.tree.getCacheKey(connection_name, key)
            cache_key_summary.size += cache_key.size
            cache_key_summary.attrs['count'] += 1

        cache_data_summary = SummaryLine(
            'Change Cache Data', connection_name, 0)
        cache_data_summary.attrs['count'] = 0
        connection_summary.add(cache_data_summary)
        for key in self.tree.listCacheData(connection_name):
            cache_data = self.tree.getCacheData(connection_name, key)
            cache_data_summary.size += cache_data.size
            cache_data_summary.attrs['count'] += 1

        sys.stdout.write(connection_summary.toStr(0, self.depth))

    def summarizeConnections(self):
        for connection_name in self.tree.listConnections():
            self.summarizeConnectionCache(connection_name)

    def summarize(self):
        self.summarizeConnections()
        self.summarizePipelines()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', help='Path to ZK dump')
    parser.add_argument('--host', help='ZK host string')
    parser.add_argument('--cert', help='Path to TLS certificate')
    parser.add_argument('--key', help='Path to TLS key')
    parser.add_argument('--ca', help='Path to TLS CA cert')
    parser.add_argument('--depth', help='Limit depth when printing')
    args = parser.parse_args()

    az = Analyzer(args)
    az.summarize()
