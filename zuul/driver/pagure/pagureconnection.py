import logging
import hmac
import hashlib
import queue
import threading
import time
import json
import cherrypy
import voluptuous as v

from zuul.connection import BaseConnection
from zuul.web.handler import BaseWebController


def _sign_request(body, secret):
    signature = 'sha1=' + hmac.new(
        secret.encode('utf-8'), body, hashlib.sha1).hexdigest()
    return signature


class PagureEventConnector(threading.Thread):
    """Move events from Pagure into the scheduler"""

    log = logging.getLogger("zuul.PagureEventConnector")

    def __init__(self, connection):
        super(PagureEventConnector, self).__init__()
        self.daemon = True
        self.connection = connection
        self._stopped = False

    def stop(self):
        self._stopped = True
        self.connection.addEvent(None)

    def _handleEvent(self):
        ts, json_body, event_type, delivery = self.connection.getEvent()
        if self._stopped:
            return
        self.log.info("Received event: %s" % str(event_type))

    def run(self):
        while True:
            if self._stopped:
                return
            try:
                self.log.info("In run loop")
                self._handleEvent()
            except Exception:
                self.log.exception("Exception moving GitHub event:")
            finally:
                self.connection.eventDone()


class PagureConnection(BaseConnection):
    driver_name = 'pagure'
    log = logging.getLogger("zuul.PagureConnection")
    payload_path = 'payload'

    def __init__(self, driver, connection_name, connection_config):
        super(PagureConnection, self).__init__(
            driver, connection_name, connection_config)
        self._change_cache = {}
        self._project_branch_cache_include_unprotected = {}
        self._project_branch_cache_exclude_unprotected = {}
        self.projects = {}
        self.server = self.connection_config.get('server', 'pagure.io')
        self.canonical_hostname = self.connection_config.get(
            'canonical_hostname', self.server)
        self.source = driver.getSource(self)
        self.event_queue = queue.Queue()

        self.sched = None

        self.installation_map = {}
        self.installation_token_cache = {}

    def onLoad(self):
        self.log.info('Starting Pagure connection: %s' % self.connection_name)
        self.log.info('Starting event connector')
        self._start_event_connector()

    def _start_event_connector(self):
        self.pagure_event_connector = PagureEventConnector(self)
        self.pagure_event_connector.start()

    def _stop_event_connector(self):
        if self.pagure_event_connector:
            self.pagure_event_connector.stop()
            self.pagure_event_connector.join()

    def addEvent(self, data, event=None, delivery=None):
        return self.event_queue.put((time.time(), data, event, delivery))

    def getEvent(self):
        return self.event_queue.get()

    def eventDone(self):
        self.event_queue.task_done()

    def maintainCache(self, relevant):
        remove = set()
        for key, change in self._change_cache.items():
            if change not in relevant:
                remove.add(key)
        for key in remove:
            del self._change_cache[key]

    def clearBranchCache(self):
        self._project_branch_cache_exclude_unprotected = {}
        self._project_branch_cache_include_unprotected = {}

    def getWebController(self, zuul_web):
        return PagureWebController(zuul_web, self)

    def validateWebConfig(self, config, connections):
        if 'webhook_token' not in self.connection_config:
            raise Exception(
                "webhook_token not found in config for connection %s" %
                self.connection_name)
        return True


class PagureWebController(BaseWebController):

    log = logging.getLogger("zuul.PagureWebController")

    def __init__(self, zuul_web, connection):
        self.connection = connection
        self.zuul_web = zuul_web
        self.token = self.connection.connection_config.get('webhook_token')

    def _validate_signature(self, body, headers):
        try:
            request_signature = headers['x-hub-signature']
        except KeyError:
            raise cherrypy.HTTPError(401, 'X-Hub-Signature header missing.')

        payload_signature = _sign_request(body, self.token)

        self.log.debug("Payload Signature: {0}".format(str(payload_signature)))
        self.log.debug("Request Signature: {0}".format(str(request_signature)))
        if not hmac.compare_digest(
            str(payload_signature), str(request_signature)):
            raise cherrypy.HTTPError(
                401,
                'Request signature does not match calculated payload '
                'signature. Check that secret is correct.')

        return True

    @cherrypy.expose
    @cherrypy.tools.json_out(content_type='application/json; charset=utf-8')
    def payload(self):
        # Note(tobiash): We need to normalize the headers. Otherwise we will
        # have trouble to get them from the dict afterwards.
        # e.g.
        # GitHub: sent: X-GitHub-Event received: X-GitHub-Event
        # urllib: sent: X-GitHub-Event received: X-Pagure-Event
        #
        # We cannot easily solve this mismatch as every http processing lib
        # modifies the header casing in its own way and by specification http
        # headers are case insensitive so just lowercase all so we don't have
        # to take care later.
        # Note(corvus): Don't use cherrypy's json_in here so that we
        # can validate the signature.
        headers = dict()
        for key, value in cherrypy.request.headers.items():
            headers[key.lower()] = value
        body = cherrypy.request.body.read()
        self._validate_signature(body, headers)
        # We cannot send the raw body through gearman, so it's easy to just
        # encode it as json, after decoding it as utf-8
        json_body = json.loads(body.decode('utf-8'))

        job = self.zuul_web.rpc.submitJob(
            'pagure:%s:payload' % self.connection.connection_name,
            {'headers': headers, 'body': json_body})

        return json.loads(job.data[0])


def getSchema():
    pagure_connection = v.Any(str, v.Schema(dict))
    return pagure_connection
