from configparser import ConfigParser
from textwrap import dedent

from unittest.mock import call
from unittest.mock import patch
from testtools import TestCase

from zuul.driver.slack.slackconnection import SlackConnection
from zuul.driver.slack.slackreporter import SlackReporter


class FakeBuildset:
    debug_messages = ['fake debug messages']


class FakePipeline:
    footer_message = 'fake footer message'
    start_message = 'fake start message'
    success_message = 'fake success message'


class FakeItem:
    change = 'fakec'
    project = 'foo/bar'
    pipeline = FakePipeline()
    current_build_set = FakeBuildset()

    # This is to make formatting this object work via **vars(item)
    def __init__(self):
        self.__dict__ = dict(vars(FakeItem))


class FakeScheduler:
    config = ConfigParser()


class TestSlack(TestCase):
    def _get_fake_connection(self):
        driver = 'slack'
        conn_name = 'testslack'
        conn_config = {
            'token': 'xop-9999999999-000000',
        }
        return SlackConnection(driver, conn_name, conn_config)

    def test_slack_connection(self):
        self._get_fake_connection()

    @patch('slackclient.SlackClient')
    def test_slack_reporter(self, _slack_mock):
        driver = 'slack'
        connection = self._get_fake_connection()
        connection.client.api_call.return_value = {
            "ok": True,
            "ts": "0.0",
        }
        connection.registerScheduler(FakeScheduler())
        config = {
            'subject': 'C{change}',
            'channel': ['#all'],
            'project-channels': [{'project': 'foo/bar', 'channel': '#foo'}],
        }
        reporter = SlackReporter(driver, connection, config)
        item = FakeItem()
        reporter.setAction('start')
        reporter.report(item)
        _slack_mock.assert_called_once_with('xop-9999999999-000000')
        report = dedent('fake start message\n'''
                        'Debug information:\n'
                        '  fake debug messages\n\n'
                        'fake footer message')
        api = 'chat.postMessage'
        calls = [
            call(api, channel="#all", as_user=True, text="Cfakec"),
            call(api, channel="#all", as_user=True, text=report,
                 thread_ts="0.0"),
            call(api, channel="#foo", as_user=True, text="Cfakec"),
            call(api, channel="#foo", as_user=True, text=report,
                 thread_ts="0.0"),
        ]
        connection.client.api_call.assert_has_calls(calls)
