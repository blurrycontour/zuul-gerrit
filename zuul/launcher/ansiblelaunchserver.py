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

import collections
import json
import logging
import multiprocessing
import os
import Queue
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import traceback
import uuid

import gear
import yaml
import jenkins_jobs.builder
import zmq


class JobDir(object):
    def __init__(self):
        self.root = tempfile.mkdtemp()
        self.git_root = os.path.join(self.root, 'git')
        os.makedirs(self.git_root)
        self.ansible_root = os.path.join(self.root, 'ansible')
        os.makedirs(self.ansible_root)
        self.inventory = os.path.join(self.ansible_root, 'inventory')
        self.playbook = os.path.join(self.ansible_root, 'playbook')
        self.post_playbook = os.path.join(self.ansible_root, 'post_playbook')
        self.config = os.path.join(self.ansible_root, 'ansible.cfg')
        self.script_root = os.path.join(self.ansible_root, 'scripts')
        os.makedirs(self.script_root)

    def __enter__(self):
        return self

    def __exit__(self, etype, value, tb):
        shutil.rmtree(self.root)


class LaunchServer(object):
    log = logging.getLogger("zuul.LaunchServer")
    section_re = re.compile('site "(.*?)"')

    def __init__(self, config):
        self.config = config
        self.hostname = socket.gethostname()
        self.node_workers = {}
        self.mpmanager = multiprocessing.Manager()
        self.jobs = self.mpmanager.dict()
        self.zmq_send_queue = multiprocessing.JoinableQueue()
        self.termination_queue = multiprocessing.JoinableQueue()
        self.sites = {}

        for section in config.sections():
            m = self.section_re.match(section)
            if m:
                sitename = m.group(1)
                d = {}
                d['host'] = config.get(section, 'host')
                d['user'] = config.get(section, 'user')
                d['pass'] = config.get(section, 'pass')
                self.sites[sitename] = d

    def start(self):
        self._gearman_running = True
        self._zmq_running = True
        self._reaper_running = True

        # Setup ZMQ
        self.zcontext = zmq.Context()
        self.zsocket = self.zcontext.socket(zmq.PUB)
        self.zsocket.bind("tcp://*:8881")

        # Setup Gearman
        server = self.config.get('gearman', 'server')
        if self.config.has_option('gearman', 'port'):
            port = self.config.get('gearman', 'port')
        else:
            port = 4730
        self.worker = gear.Worker('Zuul Launch Server')
        self.worker.addServer(server, port)
        self.log.debug("Waiting for server")
        self.worker.waitForServer()
        self.log.debug("Registering")
        self.register()

        # Load JJB config
        self.loadJobs()

        # Start ZMQ worker thread
        self.log.debug("Starting ZMQ processor")
        self.zmq_thread = threading.Thread(target=self.runZMQ)
        self.zmq_thread.daemon = True
        self.zmq_thread.start()

        # Start node worker reaper thread
        self.log.debug("Starting reaper")
        self.reaper_thread = threading.Thread(target=self.runReaper)
        self.reaper_thread.daemon = True
        self.reaper_thread.start()

        # Start Gearman worker thread
        self.log.debug("Starting worker")
        self.gearman_thread = threading.Thread(target=self.run)
        self.gearman_thread.daemon = True
        self.gearman_thread.start()

    def loadJobs(self):
        self.log.debug("Loading jobs")
        builder = JJB()
        path = self.config.get('launcher', 'jenkins_jobs')
        builder.load_files([path])
        builder.parser.expandYaml()
        unseen = set(self.jobs.keys())
        for job in builder.parser.jobs:
            self.jobs[job['name']] = job
            unseen.discard(job['name'])
        for name in unseen:
            del self.jobs[name]

    def register(self):
        self.worker.registerFunction("node-assign:zuul")

    def reconfigure(self, config):
        self.log.debug("Reconfiguring")
        self.config = config
        self.loadJobs()
        for node in self.node_workers.values():
            try:
                if node.isAlive():
                    node.queue.put(dict(action='reconfigure'))
            except Exception:
                self.log.exception("Exception sending reconfigure command to worker:")

    def stop(self):
        self.log.debug("Stopping")
        self._gearman_running = False
        self._reaper_running = False
        self.worker.shutdown()
        for node in self.node_workers.values():
            try:
                if node.isAlive():
                    node.stop()
            except Exception:
                self.log.exception("Exception sending stop command to worker:")
        self._zmq_running = False
        self.zmq_send_queue.put(None)
        self.zmq_send_queue.join()
        self.log.debug("Stopped")

    def join(self):
        self.gearman_thread.join()

    def runZMQ(self):
        while self._zmq_running or not self.zmq_send_queue.empty():
            try:
                item = self.zmq_send_queue.get()
                self.log.debug("Got ZMQ event %s" % (item,))
                if item is None:
                    continue
                self.zsocket.send(item)
            except Exception:
                self.log.exception("Exception while processing ZMQ events")
            finally:
                self.zmq_send_queue.task_done()

    def run(self):
        while self._gearman_running:
            try:
                job = self.worker.getJob()
                try:
                    if job.name.startswith('node-assign:'):
                        self.log.debug("Got assign-node job: %s" % job.unique)
                        self.assignNode(job)
                    else:
                        self.log.error("Unable to handle job %s" % job.name)
                        job.sendWorkFail()
                except Exception:
                    self.log.exception("Exception while running job")
                    job.sendWorkException(traceback.format_exc())
            except gear.InterruptedError:
                return
            except Exception:
                self.log.exception("Exception while getting job")

    def assignNode(self, job):
        args = json.loads(job.arguments)
        self.log.debug("Assigned node with arguments: %s" % (args,))
        worker = NodeWorker(self.config, self.jobs, self.sites,
                            args['name'], args['host'],
                            args['description'], args['labels'],
                            self.hostname, self.zmq_send_queue,
                            self.termination_queue)
        self.node_workers[worker.name] = worker

        worker.process = multiprocessing.Process(target=worker.run)
        worker.process.start()

        data = dict(manager=self.hostname)
        job.sendWorkData(json.dumps(data))
        job.sendWorkComplete()

    def runReaper(self):
        # We don't actually care if all the events are processed
        while self._reaper_running:
            try:
                item = self.termination_queue.get()
                self.log.debug("Got termination event %s" % (item,))
                if item is None:
                    continue
                del self.node_workers[item]
            except Exception:
                self.log.exception("Exception while processing termination events")
            finally:
                self.termination_queue.task_done()


class NodeWorker(object):
    log = logging.getLogger("zuul.NodeWorker")

    def __init__(self, config, jobs, sites, name, host, description, labels,
                 manager_name, zmq_send_queue, termination_queue):
        self.log.debug("Creating node worker %s" % (name,))
        self.config = config
        self.jobs = jobs
        self.sites = sites
        self.name = name
        self.host = host
        self.description = description
        self.labels = labels
        self.process = None
        self.registered_functions = set()
        self._running = True
        self.queue = multiprocessing.JoinableQueue()
        self.manager_name = manager_name
        self.zmq_send_queue = zmq_send_queue
        self.termination_queue = termination_queue
        self.running_job_lock = threading.Lock()
        self._job_complete_event = threading.Event()
        self._running_job = False
        self._sent_complete_event = False
        self._job_timeout = None
        self._job_start_time = None

    def isAlive(self):
        # Meant to be called from the manager
        if self.process and self.process.is_alive():
            return True
        return False

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.log.debug("Node worker %s starting" % (self.name,))
        server = self.config.get('gearman', 'server')
        if self.config.has_option('gearman', 'port'):
            port = self.config.get('gearman', 'port')
        else:
            port = 4730
        self.worker = gear.Worker(self.name)
        self.worker.addServer(server, port)
        self.log.debug("Waiting for server")
        self.worker.waitForServer()
        self.register()

        self.gearman_thread = threading.Thread(target=self.runGearman)
        self.gearman_thread.daemon = True
        self.gearman_thread.start()

        while self._running or not self.queue.empty():
            try:
                self._runQueue()
            except Exception:
                self.log.exception("Exception in queue manager:")

    def stop(self):
        # If this is called locally, setting _running will be
        # effictive, if it's called remotely, it will not be, but it
        # will be set by the queue thread.
        self.log.debug("Submitting stop request")
        self._running = False
        self.queue.put(dict(action='stop'))
        self.queue.join()

    def _runQueue(self):
        # This also runs the timeout function if needed
        try:
            item = self.queue.get(True, 10)  # 10 second resolution on timeout
        except Queue.Empty:
            # We don't need these in a critical section, but we do
            # need them not to change while we evaluate them, so make
            # local copies.
            running = self._running_job
            start = self._job_start_time
            timeout = self._job_timeout
            now = time.time()
            if (running and timeout and start
                and now - start >= timeout):
                self.log.info("Job timed out after %s seconds" % (now-start,))
                self.abortRunningJob()
            return
        try:
            if item['action'] == 'stop':
                self.log.debug("Received stop request")
                self._running = False
                self.termination_queue.put(self.name)
                if not self.abortRunningJob():
                    self.sendFakeCompleteEvent()
                else:
                    self._job_complete_event.wait()
                self.worker.shutdown()
            elif item['action'] == 'reconfigure':
                self.register()
        finally:
            self.queue.task_done()

    def runGearman(self):
        while self._running:
            try:
                self._runGearman()
            except Exception:
                self.log.exception("Exception in gearman manager:")

    def _runGearman(self):
        try:
            job = self.worker.getJob()
        except gear.InterruptedError:
            return
        self.log.debug("Node worker %s got job %s" % (self.name, job.name))
        try:
            if job.name not in self.registered_functions:
                self.log.error("Unable to handle job %s" % job.name)
                job.sendWorkFail()
                return
            self.launch(job)
        except Exception:
            self.log.exception("Exception while running job")
            job.sendWorkException(traceback.format_exc())

    def generateFunctionNames(self, job):
        # This only supports "node: foo" and "node: foo || bar"
        ret = set()
        job_labels = job.get('node')
        matching_labels = set()
        if job_labels:
            job_labels = [x.strip() for x in job_labels.split('||')]
            matching_labels = set(self.labels) & set(job_labels)
            if not matching_labels:
                return ret
        ret.add('build:%s'% (job['name'],))
        for label in matching_labels:
            ret.add('build:%s:%s' % (job['name'], label))
        return ret

    def register(self):
        if self._running_job:
            return
        new_functions = set()
        for job in self.jobs.values():
            new_functions |= self.generateFunctionNames(job)
        for function in new_functions - self.registered_functions:
            self.worker.registerFunction(function)
        for function in self.registered_functions - new_functions:
            self.worker.unRegisterFunction(function)
        self.registered_functions = new_functions

    def abortRunningJob(self):
        aborted = False
        self.log.debug("Abort: acquiring job lock")
        with self.running_job_lock:
            if self._running_job:
                self.log.debug("Abort: a job is running")
                proc = self.ansible_proc
                if proc:
                    self.log.debug("Abort: sending kill signal to job process group")
                    try:
                        pgid = os.getpgid(proc.pid)
                        os.killpg(pgid, signal.SIGKILL)
                        aborted = True
                    except Exception:
                        self.log.exception("Exception while killing ansible process:")
            else:
                self.log.debug("Abort: no job is running")

        return aborted

    def launch(self, job):
        self.log.info("Node worker %s launching job %s" % (self.name, job.name))

        # Make sure we can parse what we need from the job first
        args = json.loads(job.arguments)
        offline = True  # This may be configurable later, or we may
                        # choose to honor OFFLINE_NODE_WHEN_COMPLETE
        job_name = job.name.split(':')[1]

        # Initialize the result so we have something regardless of
        # whether the job actually runs
        result = None
        self._sent_complete_event = False

        try:
            self.sendStartEvent(job_name, args)
        except Exception:
            self.log.exception("Exception while sending job start event")

        try:
            result = self.runJob(job)
        except Exception:
            self.log.exception("Exception while launching job thread")

        self._running_job = False
        self._job_timeout = None
        self._job_start_time = None
        if not result:
            result = b''

        try:
            job.sendWorkComplete(result)
        except Exception:
            self.log.exception("Exception while sending job completion packet")

        try:
            self.sendCompleteEvent(job_name, result, args)
        except Exception:
            self.log.exception("Exception while sending job completion event")

        self._job_complete_event.set()
        if offline and self._running:
            self.stop()

    def sendStartEvent(self, name, parameters):
        build = dict(node_name=self.name,
                     host_name=self.manager_name,
                     parameters=parameters)

        event = dict(name=name,
                     build=build)

        item = "onStarted %s" % json.dumps(event)
        self.log.debug("Sending over ZMQ: %s" % (item,))
        self.zmq_send_queue.put(item)

    def sendCompleteEvent(self, name, status, parameters):
        build = dict(status=status,
                     node_name=self.name,
                     host_name=self.manager_name,
                     parameters=parameters)

        event = dict(name=name,
                     build=build)

        item = "onFinalized %s" % json.dumps(event)
        self.log.debug("Sending over ZMQ: %s" % (item,))
        self.zmq_send_queue.put(item)
        self._sent_complete_event = True

    def sendFakeCompleteEvent(self):
        if self._sent_complete_event:
            return
        self.sendCompleteEvent('zuul:launcher-shutdown',
                               'SUCCESS', {})

    def runJob(self, job):
        self.ansible_proc = None
        result = None
        with self.running_job_lock:
            if not self._running:
                return result
            self._running_job = True
            self._job_complete_event.clear()

        self.log.debug("Job %s: beginning" % (job.unique,))
        with JobDir() as jobdir:
            self.log.debug("Job %s: job root at %s" %
                           (job.unique, jobdir.root))
            self.prepareAnsibleFiles(jobdir, job)

            self._job_start_time = time.time()

            data = {
                'url': 'https://server/job',
                'number': 1
            }
            job.sendWorkData(json.dumps(data))
            job.sendWorkStatus(0, 100)

            job_status = self.runAnsiblePlaybook(jobdir)
            post_status = self.runAnsiblePostPlaybook(jobdir, job_status)
            if job_status and post_status:
                status = 'SUCCESS'
            else:
                status = 'FAILURE'

            result = json.dumps(dict(result=status))

        return result

    def getHostList(self):
        return [('node', dict(ansible_host=self.host))]

    def _makeSCPTask(self, publisher):
        tasks = []
        for scpfile in publisher['scp']['files']:
            site = publisher['scp']['site']
            if site not in self.sites:
                raise Exception("Undefined SCP site: %s" % (site,))
            site = self.sites[site]
            if scpfile.get('copy-console'):
                src = '/tmp/console.log'
            else:
                src = scpfile['source']
            syncargs = dict(src=src,
                            dest=scpfile['target'])
            task = dict(synchronize=syncargs,
                        delegate_to=site['host'])
            if not scpfile.get('copy-after-failure'):
                task['when'] = 'success'
            tasks.append(task)
        return tasks

    def _makeFTPTask(self, jobdir, publisher):
        tasks = []
        ftp = publisher['ftp']
        site = ftp['site']
        if site not in self.sites:
            raise Exception("Undefined FTP site: %s" % site)
        site = self.sites[site]
        ftproot = tempfile.mkdtemp(dir=jobdir.ansible_root)
        ftpcontent = os.path.join(ftproot, 'content')
        os.makedirs(ftpcontent)
        ftpscript = os.path.join(ftproot, 'script')
        syncargs = dict(src=ftp['source'],
                        dest=ftpcontent)
        task = dict(synchronize=syncargs,
                    when='success')
        tasks.append(task)
        task = dict(shell='lftp -f %s' % ftpscript,
                    when='success')
        ftpsource = ftpcontent
        if ftp.get('remove-prefix'):
            ftpsource = os.path.join(ftpcontent, ftp['remove-prefix'])
        while ftpsource[-1] == '/':
            ftpsource = ftpsource[:-1]
        ftptarget = ftp['target']
        while ftptarget[-1] == '/':
            ftptarget = ftptarget[:-1]
        with open(ftpscript, 'w') as script:
            script.write('open %s\n' % site['host'])
            script.write('user %s %s\n' % (site['user'], site['pass']))
            script.write('mirror -R %s %s\n' % (ftpsource, ftptarget))
        tasks.append(task)
        return tasks

    def prepareAnsibleFiles(self, jobdir, gearman_job):
        with open(jobdir.inventory, 'w') as inventory:
            for host_name, host_vars in self.getHostList():
                inventory.write(host_name)
                inventory.write(' ')
                for k, v in host_vars.items():
                    inventory.write('%s=%s' % (k, v))
                inventory.write('\n')
        job_name = gearman_job.name.split(':')[1]
        jjb_job = self.jobs[job_name]

        for wrapper in jjb_job.get('wrappers', []):
            if isinstance(wrapper, dict):
                timeout = wrapper.get('build-timeout', {})
                if isinstance(timeout, dict):
                    timeout = timeout.get('timeout')
                    if timeout:
                        self._job_timeout = timeout * 60

        with open(jobdir.playbook, 'w') as playbook:
            tasks = []
            for builder in jjb_job['builders']:
                if 'shell' in builder:
                    script_fn = '%s.sh' % str(uuid.uuid4().hex)
                    script_fn = os.path.join(jobdir.script_root, script_fn)
                    with open(script_fn, 'w') as script:
                        script.write(builder['shell'])
                    tasks.append(dict(script='%s >> /tmp/console.log 2>&1' % script_fn))
            play = dict(hosts='node', name='Job body',
                        tasks=tasks)
            playbook.write(yaml.dump([play]))

        with open(jobdir.post_playbook, 'w') as playbook:
            tasks = []
            for publisher in jjb_job.get('publishers', []):
                if 'scp' in publisher:
                    tasks.extend(self._makeSCPTask(publisher))
                if 'ftp' in publisher:
                    tasks.extend(self._makeFTPTask(jobdir, publisher))
            play = dict(hosts='node', name='Publishers',
                        tasks=tasks)
            playbook.write(yaml.dump([play]))

        with open(jobdir.config, 'w') as config:
            config.write('[defaults]\n')
            config.write('hostfile = %s\n' % jobdir.inventory)
            config.write('host_key_checking = False\n')

    def runAnsiblePlaybook(self, jobdir):
        self.ansible_proc = subprocess.Popen(
            ['ansible-playbook', jobdir.playbook],
            cwd=jobdir.ansible_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        (out, err) = self.ansible_proc.communicate()
        ret = self.ansible_proc.wait()
        self.ansible_proc = None
        return ret == 0

    def runAnsiblePostPlaybook(self, jobdir, success):
        proc = subprocess.Popen(
            ['ansible-playbook', jobdir.post_playbook, '-e', 'success=%s' % success],
            cwd=jobdir.ansible_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        (out, err) = proc.communicate()
        return proc.wait() == 0


class JJB(jenkins_jobs.builder.Builder):
    def __init__(self):
        self.global_config = None
        self._plugins_list = []
