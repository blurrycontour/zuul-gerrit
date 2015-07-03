# Copyright 2014 OpenStack Foundation
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

import json
import logging
import threading
import traceback

import gear

import merger


class MergeServer(object):
    log = logging.getLogger("zuul.MergeServer")

    def __init__(self, config):
        self.config = config
        self.zuul_url = config.get('merger', 'zuul_url')

        if self.config.has_option('merger', 'git_dir'):
            merge_root = self.config.get('merger', 'git_dir')
        else:
            merge_root = '/var/lib/zuul/git'

        if self.config.has_option('merger', 'git_user_email'):
            merge_email = self.config.get('merger', 'git_user_email')
        else:
            merge_email = None

        if self.config.has_option('merger', 'git_user_name'):
            merge_name = self.config.get('merger', 'git_user_name')
        else:
            merge_name = None

        if self.config.has_option('gerrit', 'sshkey'):
            sshkey = self.config.get('gerrit', 'sshkey')
        else:
            sshkey = None

        server = config.get('gerrit', 'server')
        user = config.get('gerrit', 'user')
        if config.has_option('gerrit', 'port'):
            port = int(config.get('gerrit', 'port'))
        else:
            port = 29418
        merge_giturl = 'ssh://%s@%s:%s' % (user, server, port)

        self.merger = merger.Merger(merge_root, sshkey,
                                    merge_email, merge_name, merge_giturl)

    def start(self):
        self._running = True
        server = self.config.get('gearman', 'server')
        if self.config.has_option('gearman', 'port'):
            port = self.config.get('gearman', 'port')
        else:
            port = 4730
        self.worker = gear.Worker('Zuul Merger')
        self.worker.addServer(server, port)
        self.log.debug("Waiting for server")
        self.worker.waitForServer()
        self.log.debug("Registering")
        self.register()
        self.log.debug("Starting worker")
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def register(self):
        self.worker.registerFunction("merger:merge")
        self.worker.registerFunction("merger:update")

    def stop(self):
        self.log.debug("Stopping")
        self._running = False
        self.worker.shutdown()
        self.log.debug("Stopped")

    def join(self):
        self.thread.join()

    def run(self):
        self.log.debug("Starting merge listener")
        while self._running:
            try:
                job = self.worker.getJob()
                try:
                    if job.name == 'merger:merge':
                        self.log.debug("Got merge job: %s" % job.unique)
                        self.merge(job)
                    elif job.name == 'merger:update':
                        self.log.debug("Got update job: %s" % job.unique)
                        self.update(job)
                    else:
                        self.log.error("Unable to handle job %s" % job.name)
                        job.sendWorkFail()
                except Exception:
                    self.log.exception("Exception while running job")
                    job.sendWorkException(traceback.format_exc())
            except Exception:
                self.log.exception("Exception while getting job")

    def merge(self, job):
        args = json.loads(job.arguments)
        for item in args['items']:
            item['url'] = self.getGitUrl(item['project'])
        commit = self.merger.mergeChanges(args['items'])
        result = dict(merged=(commit is not None),
                      commit=commit,
                      zuul_url=self.zuul_url)
        job.sendWorkComplete(json.dumps(result))

    def update(self, job):
        args = json.loads(job.arguments)
        self.merger.updateRepo(args['project'])
        result = dict(updated=True,
                      zuul_url=self.zuul_url)
        job.sendWorkComplete(json.dumps(result))

    def getGitUrl(self, project_name):
        server = self.config.get('gerrit', 'server')
        user = self.config.get('gerrit', 'user')
        if self.config.has_option('gerrit', 'port'):
            port = int(self.config.get('gerrit', 'port'))
        else:
            port = 29418
        url = 'ssh://%s@%s:%s/%s' % (user, server, port, project_name)
        return url
