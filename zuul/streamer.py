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
import aiohttp
from aiohttp import web
import functools
import json
import logging

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
    '''
    Custom Protocol Error Codes:
        1000     : Done streaming, no more data.
        4000-4009: Streamer errors
        4010-4019: Gearman errors
        4020-4029: Console communication errors
    '''

    # We don't have a context in which to pass these in, so we're going
    # to have to do property assignment on the class. Putting these
    # here just so we konw it
    gear_server = None
    gear_port = None

    def connection_made(self, transport):
        print("Connection")
        print(transport.get_extra_info('peername'))
        super(ZuulStreamerProtocol, self).connection_made(transport)
        print("after")

    def onConnect(self, request):
        print("Client connecting: {}".format(request.peer))

    def onOpen(self):
        print("WebSocket connection open")

    def onClose(self, wasClean, code, reason):
        print("Connection closed: clean=%s, code=%s, reason='%s'" %
              (wasClean, code, reason))

    def _getPortLocation(self, request):
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        rpc = zuul.rpcclient.RPCClient(self.gear_server, self.gear_port)
        return rpc.get_job_log_stream_address(request['uuid'])

    async def onMessage(self, payload, isBinary):
        print("onMessage")
        if isBinary:
            return self.sendClose(
                1003, 'zuul log streaming is a text protocol')
        try:
            await self._handleMessage(payload)
        except Exception as e:
            return self.sendClose(
                4000, "Exception handling message: %s, %s" % (e.__class__, e)
            )

    async def _handleMessage(self, payload):
        request = json.loads(payload.decode('utf8'))
        print("Got message: %s" % request)

        for key in ('uuid', 'logfile'):
            if key not in request:
                return self.sendClose(
                    4000, "'{key}' missing from request payload".format(
                        key=key))

        self.sendMessage("Test test".encode('utf8'))
        return self.sendClose(1000, "TEST TEST")

        loop = asyncio.get_event_loop()

        # Schedule the blocking gearman work in an Executor
        gear_task = loop.run_in_executor(None, self._getPortLocation, request)

        try:
            port_location = await asyncio.wait_for(gear_task, 30)
        except asyncio.TimeoutError:
            return self.sendClose(4010, "Gearman timeout")

        if not port_location:
            return self.sendClose(4011, "Error with Gearman")

        server = port_location['server']
        port = port_location['port']

        client_completed = asyncio.Future()
        client_factory = functools.partial(
            ConsoleClientProtocol, self, future=client_completed)

        try:
            factory_coroutine = await loop.create_connection(
                client_factory, host=server, port=port)

            loop.run_until_complete(factory_coroutine)
            loop.run_until_complete(client_completed)
        except Exception as e:
            print("Exception: %s" % e)
            return self.sendClose(4020, "Console streaming error")

        return self.sendClose(1000, "No more data")

async def handle_message(ws, request):
    for key in ('uuid', 'logfile'):
        if key not in request:
            await ws.close(
                4000, "'{key}' missing from request payload".format(key=key))

    ws.send_str("Test test")
    await ws.close()
    return

    loop = asyncio.get_event_loop()

    # Schedule the blocking gearman work in an Executor
    gear_task = loop.run_in_executor(None, self._getPortLocation, request)

    try:
        port_location = await asyncio.wait_for(gear_task, 30)
    except asyncio.TimeoutError:
        return self.sendClose(4010, "Gearman timeout")

    if not port_location:
        return self.sendClose(4011, "Error with Gearman")

    server = port_location['server']
    port = port_location['port']

    client_completed = asyncio.Future()
    client_factory = functools.partial(
        ConsoleClientProtocol, self, future=client_completed)

    try:
        factory_coroutine = await loop.create_connection(
            client_factory, host=server, port=port)

        loop.run_until_complete(factory_coroutine)
        loop.run_until_complete(client_completed)
    except Exception as e:
        print("Exception: %s" % e)
        return self.sendClose(4020, "Console streaming error")

    return self.sendClose(1000, "No more data")

async def websocket_handler(request):
    try:
        print("in handler")
        ws = web.WebSocketResponse()
        print("after ws")
        await ws.prepare(request)
        print("after await")
        async for msg in ws:
            print(msg.type)
            if msg.type == aiohttp.WSMsgType.TEXT:
                print("txt")
                request = json.loads(msg.data)
                print("Got message: %s" % request)
                await handle_message(ws, request)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print('ws connection closed with exception %s' %
                      ws.exception())

            print("srrsly")
            #request = json.loads(payload.decode('utf8'))
    except Exception as e:
        print(str(e))
        await ws.close()
    return ws

class ZuulStreamer(object):

    log = logging.getLogger("zuul.streamer.ZuulStreamer")

    def __init__(self, gear_server='127.0.0.1', gear_port=4730,
                 listen_address='127.0.0.1', listen_port=9000):
        self.gear_server = gear_server
        self.gear_port = gear_port
        self.listen_address = listen_address
        self.listen_port = listen_port

        #ZuulStreamerProtocol.gear_server = self.gear_server
        #ZuulStreamerProtocol.gear_port = self.gear_port

        #self.factory = websocket.WebSocketServerFactory(
        #    u"ws://{listen_address}:{listen_port}".format(
        #        listen_address=self.listen_address,
        #        listen_port=self.listen_port))
        #self.factory.protocol = ZuulStreamerProtocol

        #self.term = asyncio.Future()

        # create the server
        #coro = self.event_loop.create_server(self.factory,
        #                                     self.listen_address,
        #                                     self.listen_port)
        #self.server = self.event_loop.run_until_complete(coro)


    def run(self, loop):
        '''
        Run the websocket streamer.

        Because this method can be the target of a new thread, we need to
        set the thread event loop here, rather than in __init__().

        :param loop: The event loop to use. If not supplied, the default main
            thread event loop is used. This should be supplied if ZuulStreamer
            is run within a separate (non-main) thread.
        '''
        self.log.debug("ZuulStreamer starting")


        # The event loop must be set here before calling any autobahn methods
        # since that library will use it via calls to get_event_loop().
        if loop:
            asyncio.set_event_loop(loop)

        self.event_loop = asyncio.get_event_loop()

        app = web.Application()
        app.router.add_get('/', websocket_handler)
        web.run_app(
            app, host=self.listen_address,
            port=int(self.listen_port), loop=loop,
            handle_signals=False)

        # start the server
        #self.event_loop.run_until_complete(self.term)

        # cleanup
        self.server.close()
        #self.event_loop.stop()
        #self.event_loop.close()
        self.log.debug("ZuulStreamer stopped")

    def stop(self):
        #self.event_loop.call_soon_threadsafe(self.term.set_result, True)
        pass


if __name__ == "__main__":
    # This works
    loop = asyncio.get_event_loop()

    # This DOES NOT work
    # loop = asyncio.new_event_loop()

    z = ZuulStreamer()
    z.run(loop)
