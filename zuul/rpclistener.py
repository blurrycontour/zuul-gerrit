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

import gear
import json
import logging
import threading
import traceback

import model

class RPCListener(object):
    log = logging.getLogger("zuul.RPCListener")

    def __init__(self, config, sched):
        self.sched = sched

        server = config.get('gearman', 'server')
        if config.has_option('gearman', 'port'):
            port = config.get('gearman', 'port')
        else:
            port = 4730

        self._running = True
        self.worker = gear.Worker('Zuul RPC Listener')
        self.worker.addServer(server, port)
        self.worker.registerFunction("zuul:enqueue")

        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.log.debug("Stopping")
        self._running = False
        self.worker.shutdown()
        self.log.debug("Stopped")

    def run(self):
        while self._running:
            try:
                job = self.worker.getJob()
                z, jobname = job.name.split(':')
                attrname = 'handle_' + jobname
                if hasattr(self, attrname):
                    f = getattr(self, attrname)
                    if callable(f):
                        try:
                            f(job)
                        except Exception:
                            self.log.exception("Exception while running job")
                            job.sendWorkException(traceback.format_exc())
                    else:
                        job.sendWorkFail()
                else:
                    job.sendWorkFail()
            except Exception:
                self.log.exception("Exception while getting job")

    def handle_enqueue(self, job):
        args = json.loads(job.arguments)
        e = model.TriggerEvent()
        e.trigger_name = args['trigger']
        e.project_name = args['project']
        e.change_number = args['change']
        e.patch_number = args['patchset']
        e.forced_pipeline = args['pipeline']
        self.sched.addEvent(e)
        job.sendWorkComplete()
