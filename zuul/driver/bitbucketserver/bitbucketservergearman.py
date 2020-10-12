import logging
import json

from zuul.lib.gearworker import ZuulGearWorker


class BitbucketServerGearmanWorker(object):
    """A thread that answers gearman requests"""
    log = logging.getLogger("zuul.BitBucketServerGearmanWorker")

    def __init__(self, connection):
        self.config = connection.sched.config
        self.connection = connection
        handler = f"bitbucketserver:{self.connection.connection_name}:payload"
        self.jobs = {
            handler: self.handle_payload,
        }
        self.gearworker = ZuulGearWorker(
            'Zuul Bitbucket Server Worker',
            'zuul.BitbucketServerGearmanWorker',
            'bitbucketserver',
            self.config,
            self.jobs)

    def handle_payload(self, job):
        args = json.loads(job.arguments)
        payload = args["payload"]

        self.log.info("Bitbucket Webhook Received event: %(event)s", payload)

        try:
            self.__dispatch_event(payload)
            output = {'return_code': 200}
        except Exception:
            output = {'return_code': 503}
            self.log.exception("Exception handling Bitbucket event:")

        job.sendWorkComplete(json.dumps(output))

    def __dispatch_event(self, payload):
        self.log.info(payload)
        event = payload['event']
        try:
            self.log.info("Dispatching event %s" % event)
            self.connection.addEvent(payload, event)
        except Exception as err:
            message = 'Exception dispatching event: %s' % str(err)
            self.log.exception(message)
            raise Exception(message)

    def start(self):
        self.gearworker.start()

    def stop(self):
        self.gearworker.stop()
