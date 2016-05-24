#!/usr/bin/env python
# Copyright (c) 2016 IBM Corp.
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
# See the License for the specific language governing permissions and
# limitations under the License.


import asyncio
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass
import json

from autobahn.asyncio import websocket

import zuul.rpcclient


class ConsoleClientProtocol(asyncio.Protocol):
    def __init__(self, streamer):
        self.streamer = streamer

    def data_received(self, data):
        self.streamer.sendMessage(data)


class ZuulStreamerProtocol(websocket.WebSocketServerProtocol):

    # We don't have a context in which to pass these in, so we're going
    # to have to do property assignment on the class. Putting these
    # here just so we konw it
    gear_server = None
    gear_port = None

    @asyncio.coroutine
    def get_port_location(self, request):
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        loop = asyncio.get_event_loop()
        rpc = zuul.rpcclient.RPCClient(self.gear_server, self.gear_port)
        future = loop.run_in_executor(
            None, rpc.get_job_log_stream_address, request['uuid'])
        location = yield from future
        return location

    @asyncio.coroutine
    def onMessage(self, payload, isBinary):
        if isBinary:
            return self.sendClose(
                1003, 'zuul log streaming is a text protocol')

        request = json.loads(payload.decode('utf8'))
        for key in ('uuid', 'logfile'):
            if key not in request:
                return self.sendClose(
                    1000, "'{key}' missing from request payload".format(
                        key=key))

        try:
            # TODO: send waiting message to client?
            port_location = yield from self.get_port_location(request)
            server = port_location['server']
            port = port_location['port']
        except Exception as e:
            return self.sendClose(1000, "Exception raised: {0}".format(e))
        try:
            loop = asyncio.get_event_loop()
            coro = yield from loop.create_connection(
                lambda: ConsoleClientProtocol(self),
                host=server, port=port)
            loop.run_until_complete(coro)

        except Exception as e:
            return self.sendClose(1000, "Exception raised: {0}".format(e))
        return self.sendClose(1000, "No more data")


class ZuulStreamer(object):

    def __init__(
            self,
            gear_server='127.0.0.1', gear_port=4730,
            listen_ip='127.0.0.1', listen_port=9000):
        ZuulStreamerProtocol.gear_server = gear_server
        ZuulStreamerProtocol.gear_port = gear_port
        factory = websocket.WebSocketServerFactory(
            u"ws://{listen_ip}:{listen_port}".format(
                listen_ip=listen_ip, listen_port=listen_port))
        factory.protocol = ZuulStreamerProtocol

        loop = asyncio.get_event_loop()
        coro = loop.create_server(factory, listen_ip, listen_port)
        self.server = loop.run_until_complete(coro)

    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.server.close()
            loop.close()


if __name__ == '__main__':
    # TODO: Make a zuul/cmd/streamer.py that reads config and constructs
    #       the object based on that config
    ZuulStreamer().run()
