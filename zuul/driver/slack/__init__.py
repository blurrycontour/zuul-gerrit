
import json
import logging
import threading
from uuid import uuid4

from zuul.driver import Driver, TriggerInterface

from zuul.driver.slack.slacktrigger import SlackTrigger, getSchema
from zuul.driver.slack.slackmodel import SlackTriggerEvent


import os
import threading
import time
import traceback
import re2

from slackclient import SlackClient


RTM_READ_DELAY = 1  # 1 second delay between reading from RTM

COMMAND_REGEX = "run ([A-Za-z_/-]+) on ([A-Za-z_/-]+) branch ([A-Za-z_/-]+)"
EXAMPLE_COMMAND = "run <pipeline> on <project> branch <master>"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"


class SlackAdapter(threading.Thread):

    stopped = False
    bot_id = None

    def __init__(self, driver):
        threading.Thread.__init__(self)

        self.slack_client = None
        stoken = os.environ.get('SLACK_BOT_TOKEN', None)
        if stoken:
            self.slack_client = SlackClient(stoken)
        else:
            self.stopped = True
        self.driver = driver
        self.tenants = {}

    def run(self):
        while not self.stopped:
            try:
                self._run()
            except Exception:
                traceback.print_exc()

    def _run(self):
        if self.slack_client.rtm_connect(with_team_state=False):
            print("Slack Bot connected and running!")
            # Read bot's user ID by calling Web API method `auth.test`
            self.bot_id = self.slack_client.api_call("auth.test")["user_id"]
            while True:
                command, channel = self.parse_bot_commands(
                    self.slack_client.rtm_read())
                if command:
                    self.handle_command(command, channel)
                time.sleep(RTM_READ_DELAY)
        else:
            print("Connection failed. Exception traceback printed above.")

    def parse_bot_commands(self, slack_events):
        """Parses a list of events coming from the Slack RTM API to find bot
            commands.  If a bot command is found, this function
            returns a tuple of command and channel.  If its not found,
            then this function returns None, None.
        """

        for event in slack_events:
            if event["type"] == "message" and "subtype" not in event:
                user_id, message = self.parse_direct_mention(event["text"])
                if user_id == self.bot_id:
                    return message, event["channel"]
        return None, None

    def parse_direct_mention(self, message_text):
        """Finds a direct mention (a mention that is at the beginning) in
            message text and returns the user ID which was
            mentioned. If there is no direct mention, returns None

        """

        matches = re2.search(MENTION_REGEX, message_text)
        # the first group contains the username, the second group
        # contains the remaining message
        return (
            matches.group(1),
            matches.group(2).strip()
        ) if matches else (None, None)

    def handle_command(self, command, channel):
        """
            Executes bot command if the command is known
        """
        # Default response is help text for the user
        default_response = ("Not sure what you mean. Try *{}*."
                            .format(EXAMPLE_COMMAND))

        # Finds and executes the given command, filling in response
        response = None
        # This is where you start to implement more commands!
        m = re2.search(COMMAND_REGEX, command)
        if m:
            pipeline = m.group(1)
            project = m.group(2)
            branch = m.group(3)

            if self.callPipeline(pipeline, project, branch, channel):
                response = 'Understood, running {} on {} of {}'.format(pipeline, branch, project)
            else:
                response = 'Understood, but I can\'t do it.'
        else:
            response = 'I don\'t understand'

        # Sends the response back to the channel
        self.slack_client.api_call(
            "chat.postMessage",
            channel=channel,
            text=response or default_response
        )

    def callPipeline(self, pipeline, project, branch, channel):
        cho = self.slack_client.api_call(
            "channels.info",
            channel=channel)

        ch = cho.get('channel')
        print(ch)
        print('requesting p={}, proj={}, b={} c={} ({})'
              .format(pipeline, project, branch, channel, ch.get('name')))

        for tenant in self.tenants.keys():
            print('checking {} pipeline={} -> {}'.format(tenant, pipeline, self.tenants))
            if ch.get('name') in self.tenants[tenant][pipeline]:
                self.driver.trigger(tenant, pipeline, project, branch, [ch.get('name')])
                return True

        return False

    def registerPipeline(self, tenant, pipeline, channels):
        if tenant not in self.tenants:
            self.tenants[tenant] = {}
        self.tenants[tenant][pipeline] = channels

    def clearPipelines(self):
        self.tenants = {}


class SlackDriver(Driver, TriggerInterface):
    name = 'slack'
    log = logging.getLogger('zuul.SlackDriver')

    def __init__(self):
        self.slack = SlackAdapter(self)
        self.slack.start()

    def registerScheduler(self, scheduler):
        self.sched = scheduler

    def reconfigure(self, tenant):
        if not self.slack:
            self.slack = SlackAdapter(self)
            self.slack.start()
        self._configurePipelines(tenant)

    def _configurePipelines(self, tenant):
        # self.slack.clearPipelines()
        for pipeline in tenant.layout.pipelines.values():
            for ef in pipeline.manager.event_filters:
                if not isinstance(ef.trigger, SlackTrigger):
                    continue
                for channel in ef.channels:
                    self.slack.registerPipeline(tenant, pipeline.name, ef.channels)

    def trigger(self, tenant, pipeline_name, project, branch, channels):
        (trusted, project) = tenant.getProject(project)
        pcst = tenant.layout.getAllProjectConfigs(project.canonical_name)
        if not [True for pc in pcst if pipeline_name in pc.pipelines]:
            self.log.debug('pipeline {} not in project {} ({})'
                .format(pipeline_name, project.canonical_name, pcst))
            return

        # (trusted, project) = tenant.getProject(project)
        event = SlackTriggerEvent()
        event.type = 'slack'
        event.channels = channels
        event.forced_pipeline = pipeline_name
        event.project_hostname = project.canonical_hostname
        event.project_name = project.name
        event.ref = 'refs/heads/{}'.format(branch)
        event.branch = branch
        event.zuul_event_id = str(uuid4().hex)
        self.log.debug('Adding event')
        self.sched.addEvent(event)

    def stop(self):
        if self.slack:
            self.slack.stop()
            self.slack.join()

    def getTrigger(self, connection_name, config=None):
        return SlackTrigger(self, config)

    def getTriggerSchema(self):
        return getSchema()
