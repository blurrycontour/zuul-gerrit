from ansible.plugins.callback import CallbackBase

import os

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 1.0
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()

    def v2_on_any(self, *args, **kwargs):
        callback_success_file = os.path.join(os.path.dirname(__file__), 'test-callback-success')
        self._display.display("Touching file: {}".format(callback_success_file))
        with open(callback_success_file, 'w'):
            pass
