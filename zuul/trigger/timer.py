# Copyright 2012 Hewlett-Packard Development Company, L.P.
# Copyright 2013 OpenStack Foundation
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
import threading
import time
import urllib2
from zuul.model import TriggerEvent, Change


class TimerThread(threading.Thread):
    """Trigger events."""

    log = logging.getLogger("zuul.TimerThread")

    def __init__(self, sched):
        super(TimerThread, self).__init__()
        self.daemon = True
        self.sched = sched
        self._stopped = False
        self._changeno = 1

    def stop(self):
        self._stopped = True

    def _handleEvent(self):
        if self._stopped:
            return
        event = TriggerEvent()
        event.type = None
        event.project_name = 'org/project'
        event.ref = 'master'
        event.oldrev = '0000000000000000000000000000000000000000'
        event.newrev = 'master'
        self.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                #self._handleEvent()
                return
            except:
                self.log.exception("Exception adding timed event:")


class Timer(object):
    name = 'timer'
    log = logging.getLogger("zuul.Timer")

    def __init__(self, config, sched):
        self.sched = sched
        self.config = config
        self.timer_thread = TimerThread(sched)
        self.timer_thread.start()

    def stop(self):
        self.timer_thread.stop()
        self.timer_thread.join()

    def report(self, change, message, action):
        raise Exception("Timer trigger does not support reporting.")

    def isMerged(self, change, head=None):
        raise Exception("Timer trigger does not support checking if a change is merged.")

    def canMerge(self, change, allow_needs):
        raise Exception("Timer trigger does not support checking if a change can merge.")

    def maintainCache(self, relevant):
        return

    def getChange(self, number, patchset, refresh=False):
        raise Exception("Timer trigger does not support changes.")

    def getGitUrl(self, project):
        pass

    def getGitwebUrl(self, project, sha=None):
        url = '%s/gitweb?p=%s.git' % (self.baseurl, project)
        if sha:
            url += ';a=commitdiff;h=' + sha
        return url
