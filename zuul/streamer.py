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
import json

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from autobahn.asyncio import websocket

import zuul.rpcclient


class ConsoleClientProtocol(asyncio.Protocol):
    def __init__(self, streamer, future):
        self.streamer = streamer
        self.future = future

    def data_received(self, data):
        ''' Got data back from the finger log streamer. '''
        self.streamer.sendMessage(data)

    def eof_received(self):
        if not self.future.done():
            self.future.set_result(True)

    def connection_lost(self, exc):
        if not self.f.done():
            self.f.set_result(True)
        super().connection_lost(exc)


class ZuulStreamerProtocol(websocket.WebSocketServerProtocol):

    # We don't have a context in which to pass these in, so we're going
    # to have to do property assignment on the class. Putting these
    # here just so we konw it
    gear_server = None
    gear_port = None

    def onConnect(self, request):
        print("Client connecting: {}".format(request.peer))

    def onClose(self, wasClean, code, reason):
        print("Connection closed: clean=%s, code=%s, reason='%s'" %
              (wasClean, code, reason))

    async def _get_port_location(self, request):
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        loop = asyncio.get_event_loop()

        # Since RPCClient establishes the Gearman connection, we should
        # schedule it in the event loop. Should we keep the timeout on the
        # future? It doesn't terminate the call, but will raise an
        # asyncio.TimeoutError.
        f = loop.run_in_executor(
            None, zuul.rpcclient.RPCClient,
            self.gear_server, self.gear_port)
        rpc = await asyncio.wait_for(f, timeout=10)

        f = loop.run_in_executor(
            None, rpc.get_job_log_stream_address, request['uuid'])

        location = await f
        return location

    async def onMessage(self, payload, isBinary):
        if isBinary:
            return self.sendClose(
                1003, 'zuul log streaming is a text protocol')

        request = json.loads(payload.decode('utf8'))
        print("Got message: %s" % request)

        for key in ('uuid', 'logfile'):
            if key not in request:
                return self.sendClose(
                    1000, "'{key}' missing from request payload".format(
                        key=key))

        try:
            port_location = await self._get_port_location(request)
        except Exception as e:
            print("Exception: %s" % e)
            return self.sendClose(1000, "Error with Gearman")

        server = port_location['server']
        port = port_location['port']

        loop = asyncio.get_event_loop()

        client_completed = asyncio.Future()
        client_factory = functools.partial(
            ConsoleClient, self, future=client_completed)

        try:
            factory_coroutine = await loop.create_connection(
                client_factory, host=server, port=port)

            loop.run_until_complete(factory_coroutine)
            loop.run_until_complete(client_completed)

            #n = 10
            #while n:
            #    msg = "N is %d\n" % n
            #    print("Sending: %s" % msg)
            #    self.sendMessage(msg.encode('utf8'))
            #    n = n - 1
            #    await asyncio.sleep(2)
        except Exception as e:
            print("Exception: %s" % e)
            return self.sendClose(1000, "Console streaming error")

        return self.sendClose(0, "No more data")


class ZuulStreamer(object):

    def __init__(self, gear_server='127.0.0.1', gear_port=4730,
                 listen_ip='127.0.0.1', listen_port=9000):
        ZuulStreamerProtocol.gear_server = gear_server
        ZuulStreamerProtocol.gear_port = gear_port

        factory = websocket.WebSocketServerFactory(
            u"ws://{listen_ip}:{listen_port}".format(
                listen_ip=listen_ip, listen_port=listen_port))
        factory.protocol = ZuulStreamerProtocol

        self.event_loop = asyncio.get_event_loop()
        coro = self.event_loop.create_server(factory, listen_ip, listen_port)
        self.server = self.event_loop.run_until_complete(coro)

    def run(self):
        try:
            self.event_loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.server.close()
            self.event_loop.close()


if __name__ == '__main__':
    # TODO: Make a zuul/cmd/streamer.py that reads config and constructs
    #       the object based on that config
    ZuulStreamer().run()
