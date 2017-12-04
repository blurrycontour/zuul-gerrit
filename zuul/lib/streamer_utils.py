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


def get_port_location(rpc_client, job_uuid):
    """
    Query Gearman for the executor running the given job.

    This is a blocking call, so when using asyncio, it is expected that
    this will be scheduled in an asyncio.Executor (e.g., run_in_executor()).

    :param str job_uuid: The job UUID we want to stream.
    """
    # TODO: Fetch the entire list of uuid/file/server/ports once and
    #       share that, and fetch a new list on cache misses perhaps?
    ret = rpc_client.get_job_log_stream_address(job_uuid)
    return ret


async def finger_client(event_loop, ws, server, port, job_uuid):
    """
    Create a client to connect to the finger streamer and pull results.

    Data retrieved from the remote server are returned to the client
    until there is no more data to pull.

    :param asyncio.AbstractEventLoop event_loop: The event loop to use.
    :param aiohttp.web.WebSocketResponse ws: The websocket response object.
    :param str server: The executor server running the job.
    :param str port: The executor server port.
    :param str job_uuid: The job UUID to stream.
    """
    log = logging.getLogger('zuul.finger_client')
    log.debug("Connecting to finger server %s:%s", server, port)
    reader, writer = await asyncio.open_connection(host=server, port=port,
                                                   loop=event_loop)

    log.debug("Sending finger request for %s", job_uuid)
    msg = "%s\n" % job_uuid    # Must have a trailing newline!

    writer.write(msg.encode('utf8'))
    await writer.drain()

    while True:
        data = await reader.read(1024)
        if data:
            await ws.send_str(data.decode('utf8'))
        else:
            writer.close()
            return
