# Copyright 2011 OpenStack, LLC.
# Copyright 2012 Hewlett-Packard Development Company, L.P.
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
import paramiko
import pprint
import Queue
import select
import threading
import time


class GerritWatcher(threading.Thread):
    log = logging.getLogger("gerrit.GerritWatcher")

    def __init__(self, gerrit, username, hostname, port=29418, keyfile=None):
        threading.Thread.__init__(self)
        self.username = username
        self.keyfile = keyfile
        self.hostname = hostname
        self.port = port
        self.gerrit = gerrit

    def _read(self, fd):
        l = fd.readline()
        data = json.loads(l)
        self.log.debug("Received data from Gerrit event stream: \n%s" %
                       pprint.pformat(data))
        self.gerrit.addEvent(data)

    def _listen(self, stdout, stderr):
        poll = select.poll()
        poll.register(stdout.channel)
        while True:
            ret = poll.poll()
            for (fd, event) in ret:
                if fd == stdout.channel.fileno():
                    if event == select.POLLIN:
                        self._read(stdout)
                    else:
                        raise Exception("event on ssh connection")

    def _run(self):
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
            client.connect(self.hostname,
                           username=self.username,
                           port=self.port,
                           key_filename=self.keyfile)

            stdin, stdout, stderr = client.exec_command("gerrit stream-events")

            self._listen(stdout, stderr)

            ret = stdout.channel.recv_exit_status()
            self.log.debug("SSH exit status: %s" % ret)

            if ret:
                raise Exception("Gerrit error executing stream-events")
        except Exception:
            self.log.exception("Exception on ssh event stream:")
            time.sleep(5)

    def run(self):
        while True:
            self._run()


class Gerrit(object):
    log = logging.getLogger("gerrit.Gerrit")

    def __init__(self, hostname, username, port=29418, keyfile=None):
        self.username = username
        self.hostname = hostname
        self.port = port
        self.keyfile = keyfile
        self.watcher_thread = None
        self.event_queue = None
        self.client = None

    def startWatching(self):
        self.event_queue = Queue.Queue()
        self.watcher_thread = GerritWatcher(
            self,
            self.username,
            self.hostname,
            self.port,
            keyfile=self.keyfile)
        self.watcher_thread.start()

    def addEvent(self, data):
        return self.event_queue.put(data)

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()

    def review(self, project, change, message, action={}):
        cmd = 'gerrit review --project %s' % project
        if message:
            cmd += ' --message "%s"' % message
        for k, v in action.items():
            if v is True:
                cmd += ' --%s' % k
            else:
                cmd += ' --%s %s' % (k, v)
        cmd += ' %s' % change
        out, err = self._ssh(cmd)
        return err

    def query(self, query):
        args = '--all-approvals --comments --commit-message'
        args += ' --current-patch-set --dependencies --files'
        args += ' --patch-sets --submit-records'
        cmd = 'gerrit query --format json %s %s' % (
            args, query)
        out, err = self._ssh(cmd)
        if not out:
            return False
        lines = out.split('\n')
        if not lines:
            return False
        data = json.loads(lines[0])
        if not data:
            return False
        self.log.debug("Received data from Gerrit query: \n%s" %
                       (pprint.pformat(data)))
        return data

    def _open(self):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(self.hostname,
                       username=self.username,
                       port=self.port,
                       key_filename=self.keyfile)
        self.client = client

    def _ssh(self, command):
        if not self.client:
            self._open()

        try:
            self.log.debug("SSH command:\n%s" % command)
            stdin, stdout, stderr = self.client.exec_command(command)
        except Exception:
            self._open()
            stdin, stdout, stderr = self.client.exec_command(command)

        out = stdout.read()
        self.log.debug("SSH received stdout:\n%s" % out)

        ret = stdout.channel.recv_exit_status()
        self.log.debug("SSH exit status: %s" % ret)

        err = stderr.read()
        self.log.debug("SSH received stderr:\n%s" % err)
        if ret:
            raise Exception("Gerrit error executing %s" % command)
        return (out, err)
