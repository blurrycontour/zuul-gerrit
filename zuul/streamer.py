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


class ZuulStreamerProtocol(websocket.WebSocketServerProtocol):

    # We don't have a context in which to pass these in, so we're going
    # to have to do property assignment on the class. Putting these
    # here just so we konw it
    gear_server = None
    gear_port = None

    @asyncio.coroutine
    def get_port_location(self, request):
        loop = asyncio.get_event_loop()
        rpc = zuul.rpcclient.RPCClient(gear_server, gear_port)
        future = loop.run_in_executor(
            None, rpc.get_job_log_location, request['uuid'])
        location = yield from future
        return location

    @asyncio.coroutine
    def onMessage(self, payload, isBinary):
        if not isBinary:
            request = json.loads(payload.decode('utf8'))
            for key in ('uuid', 'logfile'):
                if key not in request:
                    self.sendClose(
                        1000, "'{key}' missing from request payload".format(
                            key=key))

            try:
                port_location = yield from self.get_port_location(request)
                server = port_location['server']
                port = port_location['port']
            except Exception as e:
                self.sendClose(1000, "Exception raised: {0}".format(e))
            try:
                async_conns = yield from asyncio.open_connection(server, port)
                remote_reader, remote_writer = async_conns
                while True:
                    line = yield from asyncio.wait_for(
                        remote_reader.readline(), timeout=10.0)
                    if not line:
                        remote_reader.close()
                        remote_writer.close()
                        break
                    response = self.sendMessage(line)
            except Exception as e:
                self.sendClose(1000, "Exception raised: {0}".format(e))
            self.sendClose(1000, "No more data")


class ZuulStreamer(object):

    def __init__(self, gear_server=None, gear_port=None):
        ZuulStreamerProtocol.gear_server = gear_server
        ZuulStreamerProtocol.gear_port = gear_port
        factory = websocket.WebSocketServerFactory(u"ws://127.0.0.1:9000")
        factory.protocol = ZuulStreamerProtocol

        loop = asyncio.get_event_loop()
        coro = loop.create_server(factory, '127.0.0.1', 9000)
        self.server = loop.run_until_complete(coro)

    def run(self):
        loop = asyncio.get_event_loop()
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
            loop.close()


if __name__ == '__main__':
    ZuulStreamer().run()
