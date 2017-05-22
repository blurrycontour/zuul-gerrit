#!/usr/bin/env python
# Copyright (c) 2017 Red Hat
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
import logging
import uvloop

import aiohttp
from aiohttp import web

from sqlalchemy.sql import select

import zuul.rpcclient


class LogStreamingHandler(object):
    log = logging.getLogger("zuul.web.LogStreamingHandler")

    def __init__(self, loop, gear_server, gear_port):
        self.event_loop = loop
        self.gear_server = gear_server
        self.gear_port = gear_port

    def _getPortLocation(self, job_uuid):
        '''
        Query Gearman for the executor running the given job.

        :param str job_uuid: The job UUID we want to stream.
        '''
        # TODO: Fetch the entire list of uuid/file/server/ports once and
        #       share that, and fetch a new list on cache misses perhaps?
        # TODO: Avoid recreating a client for each request.
        rpc = zuul.rpcclient.RPCClient(self.gear_server, self.gear_port)
        ret = rpc.get_job_log_stream_address(job_uuid)
        rpc.shutdown()
        return ret

    async def _fingerClient(self, ws, server, port, job_uuid):
        '''
        Create a client to connect to the finger streamer and pull results.

        :param aiohttp.web.WebSocketResponse ws: The websocket response object.
        :param str server: The executor server running the job.
        :param str port: The executor server port.
        :param str job_uuid: The job UUID to stream.
        '''
        self.log.debug("Connecting to finger server %s:%s", server, port)
        reader, writer = await asyncio.open_connection(host=server, port=port,
                                                       loop=self.event_loop)

        self.log.debug("Sending finger request for %s", job_uuid)
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

    async def _streamLog(self, ws, request):
        '''
        Stream the log for the requested job back to the client.

        :param aiohttp.web.WebSocketResponse ws: The websocket response object.
        :param dict request: The client request parameters.
        '''
        for key in ('uuid', 'logfile'):
            if key not in request:
                return (4000, "'{key}' missing from request payload".format(
                        key=key))

        # Schedule the blocking gearman work in an Executor
        gear_task = self.event_loop.run_in_executor(
            None, self._getPortLocation, request['uuid'])

        try:
            port_location = await asyncio.wait_for(gear_task, 10)
        except asyncio.TimeoutError:
            return (4010, "Gearman timeout")

        if not port_location:
            return (4011, "Error with Gearman")

        await self._fingerClient(
            ws, port_location['server'], port_location['port'], request['uuid']
        )

        return (1000, "No more data")

    async def processRequest(self, request):
        '''
        Handle a client websocket request for log streaming.

        :param aiohttp.web.Request request: The client request.
        '''
        try:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    req = json.loads(msg.data)
                    self.log.debug("Websocket request: %s", req)
                    code, msg = await self._streamLog(ws, req)

                    # We expect to process only a single message. I.e., we
                    # can stream only a single file at a time.
                    await ws.close(code=code, message=msg)
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.log.error(
                        "Websocket connection closed with exception %s",
                        ws.exception()
                    )
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
        except Exception as e:
            self.log.exception("Websocket exception:")
            await ws.close(code=4009, message=str(e).encode('utf-8'))
        return ws


class JobsController(object):
    def __init__(self, sql_connections):
        self.sql_connections = sql_connections

    def jobInfo(self, job_name):
        """Return all the job executions information"""
        job = {'name': job_name, 'runs': []}
        for connection in self.sql_connections.values():
            with connection.engine.begin() as conn:
                build = connection.zuul_build_table
                buildset = connection.zuul_buildset_table
                stm = select([
                    build.c.id,
                    buildset.c.pipeline,
                    buildset.c.project,
                    buildset.c.change,
                    buildset.c.patchset,
                    buildset.c.ref,
                    buildset.c.score,
                    build.c.start_time,
                    build.c.end_time,
                    build.c.log_url,
                    build.c.node_name]).\
                    where(build.c.job_name == job_name).\
                    where(build.c.buildset_id == buildset.c.id)

                for row in conn.execute(stm):
                    run = dict(row)
                    # Convert date to iso format
                    run['start_time'] = row.start_time.strftime(
                        '%Y-%m-%dT%H:%M:%S')
                    run['end_time'] = row.end_time.strftime(
                        '%Y-%m-%dT%H:%M:%S')
                    # Compute run duration
                    run['duration'] = (row.end_time -
                                       row.start_time).total_seconds()
                    job['runs'].append(run)
        return job

    def jobLists(self):
        # Return list of job similar to jenkins dashboard
        jobs = {}
        for connection in self.sql_connections.values():
            with connection.engine.begin() as conn:
                for row in conn.execute(connection.zuul_build_table.select()):
                    name, end, res = row.job_name, row.end_time, row.result
                    # Add new job to the list
                    if name not in jobs:
                        jobs[name] = {
                            'lastSuccess': end if res == 'SUCCESS' else None,
                            'lastFailure': end if res == 'FAILURE' else None,
                            'lastRun': end,
                            'lastStatus': res,
                            'lastDuration': end - row.start_time,
                            'count': 0
                        }
                    # Update job build information if relevant
                    elif res == 'SUCCESS' and (
                            not jobs[name]['lastSuccess'] or
                            jobs[name]['lastSuccess'] < end):
                        jobs[name]['lastSuccess'] = end
                    elif res == 'FAILURE' and (
                            not jobs[name]['lastFailure'] or
                            jobs[name]['lastFailure'] < end):
                        jobs[name]['lastFailure'] = end
                    if jobs[name]['lastRun'] < end:
                        jobs[name]['lastRun'] = end
                        jobs[name]['lastStatus'] = res
                    jobs[name]['count'] += 1

        jobs_list = []
        for job_name in sorted(jobs.keys()):
            job = jobs[job_name]
            jobs_list.append({
                'name': job_name,
                'status': job['lastStatus'],
                'count': job['count'],
                'lastSuccess': job['lastSuccess'].strftime(
                    '%Y-%m-%dT%H:%M:%S') if job['lastSuccess'] else None,
                'lastFailure': job['lastFailure'].strftime(
                    '%Y-%m-%dT%H:%M:%S') if job['lastFailure'] else None,
                'lastDuration': job['lastDuration'].total_seconds()})
        return jobs_list

    async def processRequest(self, request):
        try:
            if request.match_info["name"]:
                data = self.jobInfo(request.match_info["name"])
            else:
                data = self.jobLists()
            resp = web.json_response(data)
        except Exception as e:
            self.log.exception("Jobs exception:")
            resp = web.json_response({'error_description': 'Internal error'},
                                     status=500)
        return resp


class ZuulWeb(object):

    log = logging.getLogger("zuul.web.ZuulWeb")

    def __init__(self, gear_server='127.0.0.1', gear_port=4730,
                 listen_address='127.0.0.1', listen_port=9000,
                 sql_connections={}):
        self.gear_server = gear_server
        self.gear_port = gear_port
        self.listen_address = listen_address
        self.listen_port = listen_port
        if sql_connections:
            self.jobs_controller = JobsController(sql_connections)
        else:
            self.jobs_controller = None

    async def _handleWebsocket(self, request):
        handler = LogStreamingHandler(self.event_loop,
                                      self.gear_server,
                                      self.gear_port)
        return await handler.processRequest(request)

    async def _handleJobs(self, request):
        return await self.jobs_controller.processRequest(request)

    def run(self, loop=None):
        '''
        Run the websocket daemon.

        Because this method can be the target of a new thread, we need to
        set the thread event loop here, rather than in __init__().

        :param loop: The event loop to use. If not supplied, the default main
            thread event loop is used. This should be supplied if ZuulWeb
            is run within a separate (non-main) thread.
        '''
        routes = [
            ('GET', '/console-stream', self._handleWebsocket)
        ]
        if self.jobs_controller:
            routes.append(('GET', '/jobs/{name:.*}', self._handleJobs))

        self.log.debug("ZuulWeb starting")
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        user_supplied_loop = loop is not None
        if not loop:
            loop = asyncio.get_event_loop()
        asyncio.set_event_loop(loop)

        self.event_loop = loop

        app = web.Application()
        for method, path, handler in routes:
            app.router.add_route(method, path, handler)
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
