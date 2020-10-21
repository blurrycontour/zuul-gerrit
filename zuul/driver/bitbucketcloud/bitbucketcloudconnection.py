# Copyright 2019 Smaato, Inc.
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

from zuul.connection import BaseConnection
from zuul.model import Project, Branch, Ref
from zuul.driver.bitbucketcloud.bitbucketcloudmodel import (
    PullRequest, BitbucketCloudTriggerEvent)
from zuul.web.handler import BaseWebController
from zuul.driver.bitbucketcloud.bitbucketcloudsource import (
    BitbucketCloudSource)
from zuul.lib.gearworker import ZuulGearWorker
from zuul.lib.logutil import get_annotated_logger
import queue
import logging
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse
import threading
import time
import json
import uuid
import cherrypy


class BitbucketCloudConnectionError(BaseException):
    def __init__(self, message):
        self.message = message


class BitbucketCloudClient():
    log = logging.getLogger("zuul.BitbucketCloudClient")

    def __init__(self, baseurl):
        self.baseurl = baseurl

    def setCredentials(self, user, pw):
        self.user = user
        self.pw = pw

    def get(self, path):
        if path.startswith(self.baseurl):
            url = path
        else:
            url = '{}{}'.format(self.baseurl, path)

        r = requests.get(url, auth=HTTPBasicAuth(self.user, self.pw),
                         timeout=1)

        if r.status_code != 200:
            raise BitbucketCloudConnectionError(
                "Connection to server returned status {} path {}"
                .format(r.status_code, url)
            )

        response_json = r.json()

        vals = response_json.get('values')

        while 'next' in response_json.keys():

            r = requests.get(
                response_json['next'],
                auth=HTTPBasicAuth(
                    self.user,
                    self.pw),
                timeout=1)
            response_json = r.json()
            vals = vals + response_json.get('values')

        response_json['values'] = vals
        return response_json

    def post(self, path, payload=None):
        url = '{}{}'.format(self.baseurl, path)
        auth = HTTPBasicAuth(self.user, self.pw)
        if payload:
            r = requests.post(url, auth=auth,
                              json=payload, timeout=1)
        else:
            r = requests.post(url, auth=auth,
                              timeout=1,
                              json=payload)

        return r.json()

    def delete(self, path, payload=None):
        url = '{}{}'.format(self.baseurl, path)
        auth = HTTPBasicAuth(self.user, self.pw)
        if payload:
            r = requests.delete(url, auth=auth,
                                json=payload, timeout=1)
        else:
            r = requests.delete(url, auth=auth,
                                timeout=1, json=None)

        return r.status_code


class BitbucketCloudConnection(BaseConnection):
    driver_name = 'bitbucketcloud'
    log = logging.getLogger("zuul.BitbucketCloudConnection")

    def __init__(self, driver, connection_name, connection_config):
        super(BitbucketCloudConnection, self).__init__(
            driver, connection_name, connection_config)
        self.projects = {}

        self.server_user = self.connection_config.get('user')
        self.base_url = "https://api.bitbucket.org"
        self.cloneurl = "%s@bitbucket.org" % self.server_user
        self.server_pass = self.connection_config.get('password')
        self.git_ssh_key = self.connection_config.get('sshkey')
        up = urlparse(self.base_url)
        self.server = up.netloc
        self.event_queue = queue.Queue()
        self._change_cache = {}
        self.source = BitbucketCloudSource(driver, self)
        self._change_update_lock = {}
        self.branches = {}
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.base_url.split('://', 1)[-1])

    def _getBitbucketCloudClient(self):
        # authenticate, return client
        client = BitbucketCloudClient(self.base_url)
        client.setCredentials(self.server_user, self.server_pass)
        return client

    def _start_event_connector(self):
        self.bitbucketcloud_event_connector = BitbucketCloudEventConnector(
            self)
        self.bitbucketcloud_event_connector.start()

    def _stop_event_connector(self):
        if self.bitbucketcloud_event_connector:
            self.bitbucketcloud_event_connector.stop()

    def onLoad(self):
        self.log.info(
            'Starting BitbucketCloud connection: %s' %
            self.connection_name)
        self.gearman_worker = BitbucketCloudGearmanWorker(self)
        self._start_event_connector()
        self.gearman_worker.start()

    def onStop(self):
        if hasattr(self, 'gearman_worker'):
            self.gearman_worker.stop()
            self._stop_event_connector()

    def addEvent(self, data, event=None):
        return self.event_queue.put((time.time(), data, event))

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()

    def getEventQueueSize(self):
        return self.event_queue.qsize()

    def clearBranchCache(self):
        self.projects = {}

    def getProject(self, name):
        if name not in self.projects:
            self.projects[name] = Project(name, self.source)
        return self.projects.get(name)

    def getBranchSlug(self, project, id):
        self.getProjectBranches(project, 'default')

        for branch in self.branches[project].keys():
            if self.branches[project][branch].get('id') == id:
                return self.branches[project][branch].get('name')

        return None

    def getBranchSha(self, project, branch):
        self.getProjectBranches(project, 'default')

        return self.branches[project][branch].get('target').get('hash')

    def getProjectBranches(self, project, tenant):
        client = self._getBitbucketCloudClient()

        res = client.get('/2.0/repositories/{}/refs/branches'
                         .format(project))
        project_branches = self.branches.get(project, {})
        for item in res.get('values'):
            if item.get('type') == 'branch':
                project_branches[item.get('name')] = item

        self.branches[project] = project_branches

        return [item.get('name') for item in res.get('values')
                if item.get('type') == 'branch']

    def getPR(self, project_name, id):
        pr = self._getBitbucketCloudClient().get(
            '/2.0/repositories/{}/pullrequests/{}'
            .format(project_name, id)
        )
        changed_files = self._getBitbucketCloudClient().get(
            pr['links']['diffstat']['href'])
        pr['files'] = [f['new']['path'] for f in changed_files['values']]
        return pr

    def getPRs(self, project_name):
        return self._getBitbucketCloudClient().get(
            '/2.0/repositories/{}/pullrequests'
            .format(project_name)
        )

    def getChange(self, event, refresh=False):
        """Get the change representing an event."""
        project = self.source.getProject(event.project_name)

        if event.change_number:
            self.log.debug("Getting change for %s#%s" % (
                project, event.change_number))
            change = self._getChange(
                project, event.change_number, event.patch_number,
                refresh=refresh, event=event)
            change.source_event = event
            change.is_current_patchset = (change.patchset ==
                                          event.patch_number)
        else:
            if event.ref and event.ref.startswith('refs/heads'):
                change = Branch(project)
            else:
                change = Ref(project)
                change.branch = None
            change.branch = event.branch
            change.ref = event.ref
            change.oldrev = event.oldrev
            change.newrev = event.newrev
            change.source_event = event
            change.change_url = event.change_url
            change.url = event.url

        # Bitbucket Cloud does not currently support a webhook event for tags
        return change

    # Used by reporter to report commit statuses
    def setCommitStatus(self, project, sha, state, url='', description='',
                        context='', zuul_event_id=None):
        client = self._getBitbucketCloudClient()
        status_json = {
            "state": state,
            "url": url,
            "description": description,
            "key": context
        }

        endpoint = "/2.0/repositories/{}/commit/{}/statuses/build".format(
            project, sha)
        client.post(endpoint, status_json)

    def commentPull(self, project, pr_number, message, zuul_event_id=None):
        client = self._getBitbucketCloudClient()

        endpoint = "/2.0/repositories/{}/pullrequests/{}/comments".format(
            project, pr_number)
        comment_json = {"content":
                        {"raw": message}
                        }
        client.post(endpoint, comment_json)

    def reviewPull(self, project, pr_number, sha, review,
                   zuul_event_id=None):
        client = self._getBitbucketCloudClient()

        if review == "approve":
            endpoint = "/2.0/repositories/{}/pullrequests/{}/approve".format(
                project, pr_number)
            client.post(endpoint)
        elif review == "unapprove":
            # unapprove removes an approval
            endpoint = "/2.0/repositories/{}/pullrequests/{}/approve".format(
                project, pr_number)
            client.delete(endpoint)
        elif review == "decline":
            # decline closes the pull request
            endpoint = "/2.0/repositories/{}/pullrequests/{}/decline".format(
                project, pr_number)
            client.post(endpoint)

    def getHash(self, commit_url):
        client = self._getBitbucketCloudClient()
        commit_response = client.get(commit_url)
        return commit_response.get('hash')

    def _getChange(
            self,
            project,
            number,
            patch_number=None,
            refresh=False,
            url=None,
            event=None):
        log = get_annotated_logger(self.log, event)
        number = int(number)
        key = (project.name, str(number), str(patch_number))
        change = self._change_cache.get(key)
        if change and not refresh:
            return change
        if not change:
            change = PullRequest(project.name)
            change.project = project
            change.number = number
            # patch_number is the tips commit SHA of the PR
            change.patchset = patch_number
            change.url = url
            self.log.info("change url: {}".format(change.url))
            change.uris = [change.url.split('://', 1)[-1]]  # remove scheme
        self._change_cache[key] = change
        try:
            # This can be called multi-threaded during event
            # preprocessing. In order to avoid data races perform locking
            # by cached key. Try to acquire the lock non-blocking at first.
            # If the lock is already taken we're currently updating the very
            # same change right now and would likely get the same data again.
            lock = self._change_update_lock.setdefault(key, threading.Lock())
            if lock.acquire(blocking=False):
                try:
                    self._updateChange(change, event)
                finally:
                    # We need to remove the lock here again so we don't leak
                    # them.
                    lock.release()
                    del self._change_update_lock[key]
            else:
                # We didn't get the lock so we don't need to update the same
                # change again, but to be correct we should at least wait until
                # the other thread is done updating the change.
                log = get_annotated_logger(self.log, event)
                log.debug("Change %s is currently being updated, "
                          "waiting for it to finish", change)
                with lock:
                    log.debug('Finished updating change %s', change)
        except Exception:
            if key in self._change_cache:
                del self._change_cache[key]
            raise
        return change

    def _updateChange(self, change, event):
        change.pr = self.getPR(
            change.project.name, change.number)

        # Note: Bitbucket Cloud does not support refspecs on
        # pull requests currently, so instead we take the hash of the
        # the webhook objects commit, alternatively we can calculate the
        # refspec within a bespoke merger function
        # https://jira.atlassian.com/browse/BCLOUD-5814

        change.files = change.pr.get('files')
        change.branch = change.pr['source']['branch']['name']
        change.ref = event.ref
        change.title = change.pr.get('title')
        change.open = change.pr.get('state') == 'OPEN'
        message = change.pr.get("description") or ""
        if change.title:
            if message:
                message = "{}\n\n{}".format(change.title, message)
            else:
                message = change.title
        change.message = message
        change.description = change.pr.get("description")

        if not change.updated_at:
            change.updated_at = change.pr.get(
                'updated_on')
        if not change.files:
            change.files = change.pr.get('files')
            if change.files is None:
                self.log.warning("Got no files of PR.")
            elif len(change.files) < change.pr.get('changed_files', 0):
                self.log.warning("Got only %s files but PR has %s files.",
                                 len(change.files),
                                 change.pr.get('changed_files', 0))
                change.files = None

            event.changed_files
            change.files = event.changed_files

        change.url = change.pr['links']['html']['href']

        if self.sched:
            self.sched.onChangeUpdated(change, event)
        return change

    # Bitbucket Cloud Does not accept token based authentication
    # against the merge endpoint so will need to
    # investigate other auth methods
    def canMerge(self, change, allow_needs, event=None):
        return False

    def getWebController(self, zuul_web):
        return BitbucketCloudWebController(zuul_web, self)


class BitbucketCloudWebController(BaseWebController):

    log = logging.getLogger("zuul.BitbucketCloudController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web

    def _validate_webhook_headers(self, headers):
        # Bitbucket cloud does not support any auth method for their
        # webhooks, they advise to lock down sufficiently to bitbucket ips
        # for now we check all specific webhook headers are present
        headers = headers.keys()
        for header in (['x-event-key',
                        'x-hook-uuid',
                        'x-request-uuid',
                        'x-attempt-number']):
            if header not in headers:
                raise cherrypy.HTTPError(401, 'Missing: {}'.format(header))
        return True

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        self._validate_webhook_headers(headers)
        body = cherrypy.request.body.read()
        json_payload = json.loads(body.decode('utf-8'))
        job = self.zuul_web.rpc.submitJob(
            'bitbucketcloud:%s:payload' % self.connection.connection_name,
            {'headers': headers, 'body': json_payload})

        return json.loads(job.data[0])


class BitbucketCloudGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.BitbucketCloudGearmanWorker")

    def __init__(self, connection):
        self.log.info("Setting up BitbucketCloud gearman worker")
        self.config = connection.sched.config
        self.connection = connection
        handler = "bitbucketcloud:%s:payload" % self.connection.connection_name
        self.jobs = {
            handler: self.handle_payload,
        }
        self.gearworker = ZuulGearWorker(
            'Zuul BitbucketCloud Worker',
            'zuul.BitbucketCloudGearmanWorker',
            'bitbucketcloud',
            self.config,
            self.jobs)

    def handle_payload(self, job):
        args = json.loads(job.arguments)
        headers = args.get("headers")
        body = args.get("body")

        try:
            self.__dispatch_event(body, headers)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling BitbucketCloud event:")

        job.sendWorkComplete(json.dumps(output))

    def __dispatch_event(self, body, headers):
        event_type = headers['x-event-key']
        try:
            self.log.info("Dispatching event %s" % event_type)
            self.connection.addEvent(body, event_type)
        except Exception as err:
            message = 'Exception dispatching event: %s' % str(err)
            self.log.exception(message)
            raise Exception(message)

    def start(self):
        self.gearworker.start()

    def stop(self):
        self.gearworker.stop()


class BitbucketCloudEventConnector(threading.Thread):
    """Move events from Bitbucket into the scheduler"""

    log = logging.getLogger("zuul.BitbucketCloudEventConnector")

    def __init__(self, connection):
        super(BitbucketCloudEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False
        self.event_handler_mapping = {
            'pullrequest': self._event_pull_request,
            'repo': self._event_push,
        }

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    # https://support.atlassian.com/bitbucket-cloud/docs/event-payloads/
    def _event_pull_request(self, body, event_action):
        if event_action == 'comment_created':
            return self._event_pull_request_comment(body, event_action)

        event = BitbucketCloudTriggerEvent()
        pr = body.get('pullrequest')
        event.project_name = body['repository']['full_name']
        event.title = pr['title']
        event.change_number = pr['id']
        event.branch = pr['source']['branch']['name']
        event.ref = self.connection.getHash(
            pr['source']['commit']['links']['self']['href'])
        event.patch_number = event.ref
        event.change_url = pr['links']['html']['href']
        event.url = pr['links']['html']['href']

        if (event_action in ['created', 'updated', 'merged',
                             'rejected', 'approved', 'unapproved']):
            event.action = event_action
        else:
            return None
        event.type = 'bc_pull_request'
        return event

    def _event_pull_request_comment(self, body, event_action):
        event = BitbucketCloudTriggerEvent()

        if event_action != 'comment_created':
            return
        event.project_name = body['repository']['full_name']
        event.comment = body['comment']['content']['raw']

        pr = body['pullrequest']
        event.title = pr['title']
        event.change_number = pr['id']
        event.branch = pr['source']['branch']['name']
        event.ref = self.connection.getHash(
            pr['source']['commit']['links']['self']['href'])
        event.change_url = pr['links']['html']['href']
        event.patch_number = event.ref
        event.action = 'comment'
        event.type = 'bc_pull_request'
        self.log.info("Returning comment event")
        return event

    def _event_push(self, body, event_action):
        if event_action != "push":
            return
        event = BitbucketCloudTriggerEvent()
        event.project_name = body['repository']['full_name']

        # the most recent push is the first change
        push = body.get('push').get('changes')[0]
        new = push.get('new', None)
        old = push.get('old', None)

        event.url = push['links']['html']['href']
        if new is None:
            event.newrev = '0' * 40
            event.branch_deleted = True
        else:
            event.branch = new['name']
            event.newrev = new['target']['hash']

        if old is None:
            event.oldrev = '0' * 40
            event.branch_created = True

        else:
            event.branch = old['name']
            event.oldrev = old['target']['hash']

        if new is not None and old is not None:
            event.branch_updated = True
        event.type = 'bc_push'
        return event

    def _handleEvent(self):
        ts, json_body, event_type = self.connection.getEvent()
        if self._stopped:
            return

        try:
            event_name = event_type.split(':')[0]
            event_action = event_type.split(':')[1]
        except Exception:
            self.log.exception(
                'Exception when handling event: %s' % event_type)
            event = None

        self.log.info("Received event: %s" % str(event_type))

        if event_name not in self.event_handler_mapping:
            message = "Unhandled BitbucketCloud event: %s" % event_name
            self.log.info(message)
            return

        if event_name in self.event_handler_mapping:
            self.log.info("Handling event: %s" % event_type)

        try:
            event = self.event_handler_mapping[event_name](
                json_body, event_action)
        except Exception:
            self.log.exception(
                'Exception when handling event: %s' % event_type)
            event = None

        if event:
            event.zuul_event_id = str(uuid.uuid4())
            event.timestamp = ts
            if event.change_number:
                project = self.connection.source.getProject(event.project_name)
                self.connection._getChange(project,
                                           event.change_number,
                                           event.patch_number,
                                           refresh=True,
                                           url=event.change_url,
                                           event=event)
            event.project_hostname = self.connection.canonical_hostname
            self.connection.logEvent(event)
            self.log.info("Adding event to to scheduler")
            self.connection.sched.addEvent(event)

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving BitbucketCloud event:")
            finally:
                self.connection.eventDone()
