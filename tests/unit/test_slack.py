from unittest.mock import ANY
from unittest.mock import call
from tests.base import ZuulTestCase
from tests.base import simple_layout


class TestSlack(ZuulTestCase):

    @simple_layout('layouts/slack.yaml')
    def test_check_slack_report(self):
        A = self.fake_gerrit.addFakeChange('org/project', 'master', 'A')
        self.waitUntilSettled()

        self.fake_gerrit.addEvent(A.getPatchsetCreatedEvent(1))
        self.waitUntilSettled()

        self.slack_mock.assert_called_once_with('xop-9999999999-000000')
        api = 'chat.postMessage'
        calls = [
            call(api, channel="#all", as_user=True, text=ANY,
                 thread_ts=None),
            call(api, channel="#all", as_user=True, text=ANY,
                 thread_ts="0.0"),
            call(api, channel="#project", as_user=True, text=ANY,
                 thread_ts=None),
            call(api, channel="#project", as_user=True, text=ANY,
                 thread_ts="0.0"),
            call(api, channel="#all", as_user=True, text=ANY,
                 thread_ts="0.0"),
            call(api, channel="#all", as_user=True, text=ANY,
                 thread_ts="0.0"),
            call(api, channel="#project", as_user=True, text=ANY,
                 thread_ts="0.0"),
            call(api, channel="#project", as_user=True, text=ANY,
                 thread_ts="0.0"),
        ]
        self.slack_api_mock.api_call.assert_has_calls(calls)
