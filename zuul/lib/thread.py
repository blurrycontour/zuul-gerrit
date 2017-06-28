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
import threading


class Thread(threading.Thread):

    # by default if the main thread dies all threads should terminate.
    daemon = True

    # a log object that'll probably want to be overridden
    log = logging.getLogger('zuul.Thread')

    def __init__(self, *args, **kwargs):
        try:
            self.log = kwargs.pop('log')
        except KeyError:
            pass

        try:
            self.daemon = kwargs.pop('daemon')
        except KeyError:
            pass

        kwargs.setdefault('target', self.exec)
        super(Thread, self).__init__(*args, **kwargs)

    def run(self, *args, **kwargs):
        self.log.info("Thread %s starting.", self.name)

        try:
            return super(Thread, self).run(*args, **kwargs)
        except Exception:
            self.log.exception('Zuul thread %s failure', self.name)
            raise

        self.log.info("Thread %s terminated.", self.name)

    def exec(self, *args, **kwargs):
        """Override me to be run in thread by default."""
        pass
