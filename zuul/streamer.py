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

#try:
#    import uvloop
#    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
#except ImportError:
#    pass

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

        factory = websocket.WebSocketServerFactory(
            u"ws://{listen_address}:{listen_port}".format(
                listen_address=listen_address, listen_port=listen_port))
        factory.protocol = ZuulStreamerProtocol

        self.event_loop = asyncio.get_event_loop()
        coro = self.event_loop.create_server(factory, listen_address,
                                             listen_port)
        self.server = self.event_loop.run_until_complete(coro)

    def start(self):
        self.log.debug("ZuulStreamer starting")
        self.event_loop.run_forever()

    def stop(self):
        self.log.debug("ZuulStreamer stopping...")
        self.server.close()
        self.event_loop.close()

        # When not daemonized, this works as expected.
        # But when daemonized:
        #   - With uvloop, we never get here. The event_loop.close() hangs.
        #
        #   - Without uvloop, the event_loop.close() throws the exception:
        #
        #        RuntimeError: Cannot close a running event loop

        self.log.debug("ZuulStreamer stopped")


if __name__ == '__main__':
    # TODO: Make a zuul/cmd/streamer.py that reads config and constructs
    #       the object based on that config
    ZuulStreamer().run()
