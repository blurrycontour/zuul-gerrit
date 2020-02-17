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

import logging
import openstack
import os

NOT_FOUND = b'''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>404 Not Found</title>
</head><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
</body></html>
'''

METHOD_NOT_ALLOWED = b'''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>405 Method Not Allowed</title>
</head><body>
<h1>Method Not Allowed</h1>
<p>The requested method is not supported.</p>
</body></html>
'''

FORBIDDEN = b'''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>403 Forbidden</title>
</head><body>
<h1>Forbidden</h1>
<p>Overwriting files is not allowed.</p>
</body></html>
'''

BACKEND_CONNECTION = b'''<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>503</title>
</head><body>
<h1>Backend problem</h1>
<p>Backend connection failed.</p>
</body></html>
'''


def redirect_directory(start_response, path):
    # We need to redirect with the last element plus a terminating '/'
    last_element = os.path.basename(path.rstrip('/'))
    redirect = last_element + '/'

    start_response(
        '301 Moved Permanently',
        [('Location', redirect)]
    )
    return iter([b''])


def data_generator(data):
    chunk_size = 16384
    buf = data.read(chunk_size)
    while buf:
        yield buf
        buf = data.read(chunk_size)


def handle_get(start_response, clouds, container, path):
    failures = []
    for cloud in clouds:
        with cloud.object_store.get(
                '%s/%s' % (container, path),
                stream=True) as response:
            response_headers = {k: v for k, v in response.headers.items()}

            if response.status_code == 404:
                failures.append((404, ''))
                continue
            elif response.status_code != 200:
                failures.append((response.status_code, response.reason))
                continue

                data = b'Status code %s' % str(response.status_code).encode()
                start_response(
                    "{} {}".format(response.status_code, response.reason),
                    [('Content-Length', str(len(data)))]
                )
                yield data
                return

            if response_headers['Content-Type'] == 'application/directory':
                # We got a directory so redirect it to path/index.html
                return redirect_directory(start_response, path)

            start_response(
                "{} {}".format(response.status_code, response.reason),
                response_headers.items())

            # We want to forward the compressed data stream here so use the raw
            # response stream.
            while response.raw:
                data = response.raw.read(16384)
                yield data
                if len(data) == 0:
                    break
            return

    # When hitting a special failure in one cloud return this,
    # otherwise return 404
    for status_code, reason in failures:
        if status_code == 404:
            # handle later
            continue

        # We hit a special failure, report this
        data = b'Status code %s' % str(status_code).encode()
        start_response(
            "{} {}".format(status_code, reason),
            [('Content-Length', str(len(data)))]
        )
        yield data
        return

    # No special failure, return 404
    start_response(
        '404 Not Found', []
    )
    yield NOT_FOUND
    return


def handle_put(environ, start_response, clouds, container, path):
    # Only upload to first cloud for now
    cloud = clouds[0]
    subdir = os.path.basename(os.path.dirname(path))
    if subdir not in ('log-analysis-results'):
        # Only allow content in <buildlog>/log-analysis-results/ to be
        # overwritten.
        try:
            obj = cloud.object_store.get_object(path, container=container)
        except openstack.exceptions.ResourceNotFound:
            # We expect this exception during normal operations
            obj = None

        if obj is not None:
            start_response(
                '403 Forbidden', []
            )
            yield FORBIDDEN
            return

    data = data_generator(environ['wsgi.input'].reader)
    try:
        cloud.object_store.upload_object(
            container, path, data=data)
    except openstack.exceptions.OpenStackCloudException:
        start_response(
            '503 Failed to upload object', []
        )
        yield BACKEND_CONNECTION

    start_response(
        '200 OK', []
    )
    yield b''


def swift_proxy(environ, start_response, clouds, container_prefix):
    path = environ['PATH_INFO'].lstrip('/')
    method = environ['REQUEST_METHOD']

    # If the path ends with a / this is a directory and we want to deliver the
    # index.html instead.
    if path.endswith('/'):
        path += 'index.html'

    components = path.split('/', 1)

    if not path:
        start_response(
            '404 Not Found', []
        )
        yield NOT_FOUND
        return

    if len(components) < 2:
        # no path inside tenant given, redirect to root index
        return redirect_directory(start_response, path)

    tenant = components[0]
    path = components[1]
    container = '-'.join([container_prefix, tenant])

    print('%s request %s/%s' % (method, container, path))
    try:
        if method == 'GET':
            for chunk in handle_get(start_response, clouds, container, path):
                yield chunk
        elif method == 'PUT':
            for chunk in handle_put(environ, start_response, clouds, container,
                                    path):
                yield chunk
        else:
            start_response(
                '405 Method Not Allowed', []
            )
            yield METHOD_NOT_ALLOWED
    except Exception as e:
        start_response(
            '503 Backend connection failed', []
        )
        yield '{}\n'.format(e).encode()


class CloudCache(object):

    def __init__(self, app):
        self.log = logging.getLogger('middleware')
        self.app = app

        if 'CLOUD_NAME' in os.environ:
            cloud_names = [os.environ['CLOUD_NAME']]
        else:
            cloud_names = os.environ['CLOUD_NAMES'].split(',')

        self.clouds = []
        for cloud_name in cloud_names:
            self.log.warning('Using cloud %s', cloud_name)
            self.clouds.append(openstack.connect(cloud=cloud_name))
        self.container_prefix = os.environ['CONTAINER_PREFIX']
        self.log.warning('Using container prefix %s', self.container_prefix)

    def __call__(self, environ, start_response):
        for chunk in self.app(environ, start_response, self.clouds,
                              self.container_prefix):
            yield chunk


proxy = CloudCache(swift_proxy)
