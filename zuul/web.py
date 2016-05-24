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
import functools
import json
import logging
import uvloop

import aiohttp
from aiohttp import web

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


class ZuulWeb(object):

    log = logging.getLogger("zuul.web.ZuulWeb")

    def __init__(self, gear_server='127.0.0.1', gear_port=4730,
                 listen_address='127.0.0.1', listen_port=9000):
        self.gear_server = gear_server
        self.gear_port = gear_port
        self.listen_address = listen_address
        self.listen_port = listen_port

    async def _handleWebsocket(self, request):
        try:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    request = json.loads(msg.data)
                    self.log.debug("Websocket request: %s", request)
                    code, msg = await self._handleMessage(ws, request)
                    await ws.close(code=code, message=msg)
                    return ws
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log.error(
                        "Websocket connection closed with exception %s",
                         ws.exception()
                    )
        except Exception as e:
            self.log.exception("Websocket exception:")
            await ws.close(code=4009, message=str(e).encode('utf-8'))
        return ws

    def _getPortLocation(self, request):
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        rpc = zuul.rpcclient.RPCClient(self.gear_server, self.gear_port)
        return rpc.get_job_log_stream_address(request['uuid'])

    async def _handleMessage(self, ws, request):
        for key in ('uuid', 'logfile'):
            if key not in request:
                return (4000, "'{key}' missing from request payload".format(
                        key=key))

        ws.send_str("Test test")
        return (1000, "Stream finished")

        # Schedule the blocking gearman work in an Executor
        gear_task = self.event_loop.run_in_executor(
            None, self._getPortLocation, request)

        try:
            port_location = await asyncio.wait_for(gear_task, 30)
        except asyncio.TimeoutError:
            return (4010, "Gearman timeout")

        if not port_location:
            return (4011, "Error with Gearman")

        server = port_location['server']
        port = port_location['port']

        client_completed = asyncio.Future()
        client_factory = functools.partial(
            ConsoleClientProtocol, self, future=client_completed)

        try:
            factory_coroutine = await self.event_loop.create_connection(
                client_factory, host=server, port=port)

            self.event_loop.run_until_complete(factory_coroutine)
            self.event_loop.run_until_complete(client_completed)
        except Exception as e:
            print("Exception: %s" % e)
            return (4020, "Console streaming error")

        return (1000, "No more data")

    def run(self, loop=None):
        '''
        Run the websocket daemon.

        Because this method can be the target of a new thread, we need to
        set the thread event loop here, rather than in __init__().

        :param loop: The event loop to use. If not supplied, the default main
            thread event loop is used. This should be supplied if ZuulWeb
            is run within a separate (non-main) thread.
        '''
        self.log.debug("ZuulWeb starting")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        user_supplied_loop = loop is not None
        if not loop:
            loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)

        self.event_loop = loop

        app = web.Application()
        app.router.add_get('/console-stream', self._handleWebsocket)
        handler = app.make_handler(loop=self.event_loop)

        # create the server
        coro = self.event_loop.create_server(handler,
                                             self.listen_address,
                                             self.listen_port)
        self.server = self.event_loop.run_until_complete(coro)

        self.term = asyncio.Future()

        # start the server
        self.event_loop.run_until_complete(self.term)

        # cleanup
        self.log.debug("ZuulWeb stopping")
        self.server.close()
        self.event_loop.run_until_complete(self.server.wait_closed())
        self.event_loop.run_until_complete(app.shutdown())
        self.event_loop.run_until_complete(handler.shutdown(60.0))
        self.event_loop.run_until_complete(app.cleanup())
        self.log.debug("ZuulWeb stopped")

        # Only run these if we are controlling the loop - they need to be
        # run from the main thread
        if not user_supplied_loop:
            loop.stop()
            loop.close()

    def stop(self):
        self.event_loop.call_soon_threadsafe(self.term.set_result, True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    z = ZuulWeb()
    z.run(loop)
