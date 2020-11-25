# Copyright 2020 BMW Group
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

import io
from contextlib import suppress
from typing import List

from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

# The default size limit for a node in Zookeeper is 1MiB. However, as this
# also includes the size of the key we can not use all of the 1048576 bytes.
NODE_BYTE_SIZE_LIMIT = 1000000


class ShardedRawIO(io.RawIOBase):
    def __init__(self, client: KazooClient, path: str):
        self.client = client
        self.shard_base = path

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def truncate(self):
        with suppress(NoNodeError):
            self.client.delete(self.shard_base, recursive=True)

    @property
    def _shards(self) -> List[str]:
        try:
            return self.client.get_children(self.shard_base)
        except NoNodeError:
            return []

    def readall(self) -> bytes:
        read_buffer = io.BytesIO()
        for shard_name in sorted(self._shards):
            shard_path = "/".join((self.shard_base, shard_name))
            data, _ = self.client.get(shard_path)
            read_buffer.write(data)
        return read_buffer.getvalue()

    def write(self, shard_data) -> int:
        byte_count = len(shard_data)
        # Only write one key at a time and defer writing the rest to the caller
        shard_bytes = bytes(shard_data[0:NODE_BYTE_SIZE_LIMIT])
        self.client.create(
            "{}/".format(self.shard_base),
            shard_bytes,
            sequence=True,
            makepath=True,
        )
        return min(byte_count, NODE_BYTE_SIZE_LIMIT)


class BufferedShardIO(io.TextIOBase):
    def __init__(self, client: KazooClient, path: str):
        self._raw = ShardedRawIO(client, path)
        self._writer = io.BufferedWriter(
            self._raw,
            NODE_BYTE_SIZE_LIMIT,
        )

    def __enter__(self) -> "BufferedShardIO":
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def close(self) -> None:
        self._writer.close()

    def flush(self) -> None:
        self._writer.flush()

    def write(self, data: str) -> int:
        return self._writer.write(data.encode("utf8"))

    def read(self, size=-1) -> str:
        self.flush()
        return self._raw.readall().decode("utf8")

    def truncate(self, size=None) -> int:
        self.flush()
        return self._raw.truncate()
