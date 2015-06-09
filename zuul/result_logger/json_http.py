# Copyright 2015 Jan Kundrát <jkt@kde.org>
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

import copy
import exceptions
import json
import logging
import requests
import uuid


class ResultLogger(object):
    """Save JSON-formatted data via HTTP request upon each event."""

    name = 'json_http'
    log = logging.getLogger("zuul.result_logger.json_http.ResultLogger")

    def __init__(self):
        self.url = None
        self.method = None

    def get(self, params):
        """Set up the reporter.

        The URL can contain placeholders {project}, {pipeline} and {id}.

        Method must be either POST or PUT.
        """

        res = copy.copy(self)
        res.url = params['url']
        res.method = params['method']
        if params['method'] == 'POST':
            res.f = requests.post
        elif params['method'] == 'PUT':
            res.f = requests.put
        else:
            raise exceptions.ValueError('method must be POST or PUT')

        return res

    def save(self, item):
        """Send the machine-readable data via HTTP POST."""

        url = self.url.format(project=item.change.project.name,
                              pipeline=item.pipeline.name, id=item.change._id(),
                              uuid=uuid.uuid4()
                             )
        self.log.debug("Saving %s: %s %s" % (item.change, self.method,
                                             url))
        r = self.f(url, data=json.dumps(item.formatJSON()),
                   headers={'Content-Type': 'text/json'})
        if r.status_code < 200 or r.status_code > 299:
            self.log.debug('HTTP error %s: %s' % (r.status_code, r.reason))
            return 'HTTP error'
        return

    def __repr__(self):
        return '<json_http.ResultLogger 0x%x: %s %s>' % (id(self), self.method,
                                                         self.url)
