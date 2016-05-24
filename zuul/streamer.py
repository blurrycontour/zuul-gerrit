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

    def onConnect(self, request):
        print("Client connecting: {}".format(request.peer))

    def onClose(self, wasClean, code, reason):
        print("Connection closed: clean=%s, code=%s, reason='%s'" %
              (wasClean, code, reason))

    def _getPortLocation(self, request):
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        rpc = zuul.rpcclient.RPCClient(self.gear_server, self.gear_port)
        return rpc.get_job_log_stream_address(request['uuid'])

    async def onMessage(self, payload, isBinary):
        if isBinary:
            return self.sendClose(
                1003, 'zuul log streaming is a text protocol')

        request = json.loads(payload.decode('utf8'))
        print("Got message: %s" % request)

        for key in ('uuid', 'logfile'):
            if key not in request:
                return self.sendClose(
                    4000, "'{key}' missing from request payload".format(
                        key=key))

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

            # n = 10
            # while n:
            #     msg = "N is %d\n" % n
            #     print("Sending: %s" % msg)
            #     self.sendMessage(msg.encode('utf8'))
            #     n = n - 1
            #     await asyncio.sleep(2)
        except Exception as e:
            print("Exception: %s" % e)
            return self.sendClose(4020, "Console streaming error")

        return self.sendClose(1000, "No more data")


class ZuulStreamer(object):

    log = logging.getLogger("zuul.streamer.ZuulStreamer")

    def __init__(self, gear_server='127.0.0.1', gear_port=4730,
                 listen_address='127.0.0.1', listen_port=9000):
        ZuulStreamerProtocol.gear_server = gear_server
        ZuulStreamerProtocol.gear_port = gear_port
        self.listen_address = listen_address
        self.listen_port = listen_port

        self.factory = websocket.WebSocketServerFactory(
            u"ws://{listen_address}:{listen_port}".format(
                listen_address=listen_address, listen_port=listen_port))
        self.factory.protocol = ZuulStreamerProtocol

    def run(self, loop=None):
        '''
        Run the websocket streamer.

        :param loop: The event loop to use. If not supplied, the default main
            thread event loop is used. This should be supplied if ZuulStreamer
            is run within a separate (non-main) thread.
        '''
        self.log.debug("ZuulStreamer starting")

        if loop:
            self.event_loop = loop
            asyncio.set_event_loop(self.event_loop)
        else:
            self.event_loop = asyncio.get_event_loop()

        self.term = asyncio.Future()

        # create the server
        coro = self.event_loop.create_server(self.factory,
                                             self.listen_address,
                                             self.listen_port)
        self.server = self.event_loop.run_until_complete(coro)

        # start the server
        self.event_loop.run_until_complete(self.term)

        # cleanup
        self.server.close()
        self.event_loop.stop()
        self.event_loop.close()
        self.log.debug("ZuulStreamer stopped")

    def stop(self):
        self.event_loop.call_soon_threadsafe(self.term.set_result, True)
